# /// script
# requires-python = ">=3.10"
# ///
"""Per kernel call of Inductor-compiled graphs: the ops and source lines it covers, and AC recompute vs backward.

Reads graph directories of a `TORCH_COMPILE_DEBUG=1` run (`<debug dir>/torch_compile_debug/run_*/torchinductor/
model__<n>_{forward,backward,inference}_*`, one `run_*` directory per rank): `fx_graph_transformed.py`, the post-grad
graph, and `inductor_provenance_tracking_node_mappings.json`, whose `cppCodeToPost` maps each call in the generated
code (Triton kernel, extern GEMM, custom op) to the post-grad nodes it computes. Per node, the post-grad graph gives the
op (`aten.mm`, `prime_rl.kda_chunk`) and the preceding `File: <path>:<line> in <fn>, code: ...` comment (inside
activation-checkpointed regions prefixed `ac_graph_id: <n> - PREFER_RECOMPUTE`). In a backward graph (one with
`tangents_*` inputs) a node is backward when it depends, transitively, on a tangent, and a call is recompute when none
of its nodes is: the checkpointed forward replayed inside the backward. A backward graph's provenance file also lists
the calls of the forward graph compiled with it, so those (the sibling `model__<n>_forward_*` directory's) are dropped.

Prints one section per graph and one entry per kernel name: its calls (recompute / backward in a backward graph), the
ops of its nodes, and their source lines (`--strip PREFIX` removes a path prefix). `--kernel REGEX` keeps matching
kernel names. `--recompute-json OUT` writes `{LABEL: [Triton kernels with a recompute call]}` over the backward graphs
for `layer_inventory.py --recompute-kernels`; Inductor kernel names repeat across graphs, so label each backward graph
with the layer type it compiles (`DIR=LABEL`, default the directory name). `--gemm-sequence-json OUT` writes
`{LABEL: [true if recompute, per extern GEMM call (mm, addmm, bmm, _grouped_mm, ...) in call order]}` over the backward
graphs for `layer_inventory.py --recompute-gemms`, which needs it where gradient GEMMs share a forward GEMM's shapes.

Usage: uv run --script inductor_kernels.py GRAPH_DIR[=LABEL] [GRAPH_DIR[=LABEL] ...] [--kernel REGEX]
         [--strip PREFIX] [--recompute-json recompute.json] [--gemm-sequence-json gemms.json]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

ASSIGN = re.compile(r'^\s+(\w+)(?:: "[^"]*")? = (.*)$')
IDENT = re.compile(r"\b([A-Za-z_]\w*)\b")
OP = re.compile(r"^torch\.ops\.(\w+\.\w+)")
FILE = re.compile(r"File: (\S+):(\d+) in (\w+), code: (.*)$")
EXTERN_GEMM = re.compile(r"^extern_kernels\.(mm|addmm|bmm|baddbmm|_grouped_mm|_scaled_mm|mm_dtype)$")


def parse_graph(path, strip):
    """Per post-grad node: its op, its source line, and whether it depends on a tangent input."""
    ops, sources, backward = {}, {}, set()
    source = None
    with open(path) as f:
        for line in f:
            if line.strip().startswith("#"):
                found = FILE.search(line)
                source = f"{found[1].removeprefix(strip)}:{found[2]} {found[4].strip()[:70]}" if found else None
                continue
            found = ASSIGN.match(line)
            if not found:
                continue
            name, rhs = found[1], found[2].split(";")[0]
            op = OP.match(rhs)
            if op:
                ops[name] = op[1]
            if source:
                sources[name] = source
            if any(ref.startswith("tangents_") or ref in backward for ref in IDENT.findall(rhs)):
                backward.add(name)
    return ops, sources, backward


def forward_graph_calls(path):
    """Calls of the forward graph compiled with this backward graph (sibling `model__<n>_forward_*`), which the
    backward graph's provenance file lists again ahead of its own."""
    found = re.match(r"(model__\d+)_backward_", os.path.basename(path.rstrip("/")))
    if not found:
        return []
    parent = os.path.dirname(path.rstrip("/"))
    calls = []
    for sibling in os.listdir(parent):
        mappings = os.path.join(parent, sibling, "inductor_provenance_tracking_node_mappings.json")
        if sibling.startswith(f"{found[1]}_forward_") and os.path.exists(mappings):
            with open(mappings) as f:
                calls += list(json.load(f)["cppCodeToPost"])
    return calls


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("graphs", nargs="+", metavar="GRAPH_DIR[=LABEL]")
    p.add_argument("--kernel", default="", help="regex of kernel names to print")
    p.add_argument("--strip", default="", help="path prefix removed from source lines")
    p.add_argument("--recompute-json", default=None)
    p.add_argument("--gemm-sequence-json", default=None)
    args = p.parse_args()
    kernel_rx = re.compile(args.kernel)
    recompute, gemm_sequence = {}, {}
    for spec in args.graphs:
        path, _, label = spec.partition("=")
        label = label or os.path.basename(path.rstrip("/"))
        mappings = os.path.join(path, "inductor_provenance_tracking_node_mappings.json")
        if not os.path.exists(mappings):
            sys.exit(f"{mappings} is missing: capture with TORCH_COMPILE_DEBUG=1")
        with open(mappings) as f:
            calls = json.load(f)["cppCodeToPost"]
        for call in forward_graph_calls(path):
            calls.pop(call, None)
        ops, sources, backward = parse_graph(os.path.join(path, "fx_graph_transformed.py"), args.strip)
        is_backward_graph = bool(backward)
        counts = defaultdict(lambda: {"recompute": 0, "backward": 0, "calls": 0})
        nodes = defaultdict(set)
        for call, call_nodes in calls.items():
            kernel = call.rsplit(":", 1)[0]
            nodes[kernel].update(call_nodes)
            counts[kernel]["calls"] += 1
            counts[kernel]["backward" if any(n in backward for n in call_nodes) else "recompute"] += 1
        if is_backward_graph:
            recompute[label] = sorted(k for k, c in counts.items() if c["recompute"] and k.startswith("triton_"))
            ordered = sorted(calls.items(), key=lambda kv: int(kv[0].rsplit(":", 1)[1]))
            gemm_sequence[label] = [not any(n in backward for n in call_nodes) for call, call_nodes in ordered
                                    if EXTERN_GEMM.match(call.rsplit(":", 1)[0])]
        print(f"## {label} ({'backward' if is_backward_graph else 'forward or inference'} graph): `{path}`\n")
        for kernel in sorted(k for k in counts if kernel_rx.search(k)):
            c = counts[kernel]
            calls_text = f"recompute {c['recompute']}, backward {c['backward']}" if is_backward_graph else f"{c['calls']} calls"
            kernel_ops = sorted({ops[n] for n in nodes[kernel] if n in ops})
            print(f"- `{kernel}`: {calls_text}; ops: {', '.join(kernel_ops) or '-'}")
            for source in sorted({sources[n] for n in nodes[kernel] if n in sources}):
                print(f"  - {source}")
        print()
    if args.recompute_json:
        with open(args.recompute_json, "w") as f:
            json.dump(recompute, f, indent=1)
        print(f"wrote {args.recompute_json}")
    if args.gemm_sequence_json:
        with open(args.gemm_sequence_json, "w") as f:
            json.dump(gemm_sequence, f)
        print(f"wrote {args.gemm_sequence_json}")


if __name__ == "__main__":
    main()
