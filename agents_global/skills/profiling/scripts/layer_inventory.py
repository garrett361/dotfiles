# /// script
# requires-python = ">=3.10"
# ///
"""Per layer type and pass, GPU launches and time by kernel class, plus chains of small kernels, from a torch trace.

Every kernel, memcpy and memset launched (host time, joined via `args["correlation"]`) from the start of the
`--annotation-index`th CPU-side `user_annotation` named `--annotation` (default `forward`, also matching `forward#<n>`)
to the start of the next `user_annotation` matching the regex `--end-annotation` (default `^Optimizer\\.step`,
torch.optim's step range) is assigned:
- a segment: the latest host event on the launch's thread, at or before the launch, matching `--segment`. Its named
  group `segment` names the segment (a layer), and its named group `pass` sets the pass: backward if that text
  contains "backward", else forward. The default matches FSDP2's per-module hooks `FSDP::pre_forward (<module>)` and
  `FSDP::pre_backward (<module>)`. Kernels launched before the first segment are dropped.
- a layer type: the first `--layer-type REGEX=LABEL` whose regex matches the segment name, else the segment name.
- a class, first match wins: `nccl` (kernel name matches `--comm`); each `--class LABEL:REGEX`, matched against
  `<host stack> [<dims>] : <kernel name>` as in `top_kernels.py --category-context`; `gemm` (name matches `--gemm`,
  or the innermost cpu_op is an ATen GEMM); `custom` (launched inside a namespaced op outside torch's namespaces,
  e.g. `prime_rl::...`, `flash_attn_3::...`); `inductor` (`triton_*`); `copy` (memcpy, memset); `eager` (the rest).
  Custom comes before inductor because the profiler can name a custom op's Triton kernel like an Inductor kernel.
- a recompute flag (activation checkpointing): a backward-pass kernel moves to pass `recompute` when its custom op's
  name does not match `--backward-op`, when it is a GEMM whose input dims equal a forward GEMM's in the same layer
  type, or when it is an Inductor kernel listed for its layer type in `--recompute-kernels` (JSON
  `{"<layer type>": [kernel names]}`, from `inductor_kernels.py --recompute-json`). The GEMM rule misfiles gradient
  GEMMs shaped like forward ones, so totals over passes are exact and the pass split is approximate.

Output, per step if the window is one step (with K micro-batches per step, `--annotation-index -K`): launches / GPU ms
per (layer type, pass) and class, with a total over the classes not in `--total-skip` and the share launched outside
compiled regions; the same per layer type over all passes; then chains: maximal runs of at least `--min-chain`
consecutive kernels on the main compute stream within one segment invocation, each of a class in `--chain-classes` and
shorter than `--small-us`, grouped by (layer type, pass, kernel sequence) with the kernel or custom op before and after.
Each chain gets a fused-pass floor, its largest kernel's argument bytes (`top_kernels.py --arg-bytes`) read once at
`--hbm-tbps`; recoverable = chain time minus that floor, an upper bound on what one fused kernel saves. `--csv-prefix P`
writes `P_inventory.csv`, `P_chains.csv` and `P_kernels.csv` (one row per kernel).

Usage: uv run --script layer_inventory.py <trace.json.gz> [--annotation forward] [--annotation-index -1]
         [--end-annotation '^Optimizer\\.step'] [--segment REGEX] [--layer-type REGEX=LABEL ...]
         [--class LABEL:REGEX ...] [--comm nccl] [--gemm REGEX] [--backward-op 'backward|bwd']
         [--recompute-kernels recompute.json] [--total-skip nccl] [--chain-classes inductor,eager,copy]
         [--small-us 50] [--min-chain 2] [--hbm-tbps 3.0] [--top-chains 40] [--csv-prefix PREFIX]
  prime-rl classes: projects/prime-rl.md.
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict

from top_kernels import GPU_CATS, WRAPPER_OPS, arg_bytes, compact_dims, short_name
from trace_events import LAUNCH_CATEGORIES, is_marker, latest_marks, launch_context, launch_stacks, pick, read_trace

GEMM_OP = re.compile(r"^aten::(mm|addmm|bmm|baddbmm|_grouped_mm|_scaled_mm|matmul|linear)$")
TORCH_NAMESPACES = ("aten::", "c10d::", "FSDP::", "fsdp::", "autograd::", "profiler::", "cuda::", "torch::")
COMPILED = ("Torch-Compiled Region", "CompiledFunction", "## Call CompiledFxGraph")
BUILTIN_CLASSES = ["inductor", "eager", "custom", "gemm", "copy"]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("trace")
    p.add_argument("--annotation", default="forward")
    p.add_argument("--annotation-index", type=int, default=-1, help="which --annotation opens the window")
    p.add_argument("--end-annotation", default=r"^Optimizer\.step", help="regex of the user_annotation closing it")
    p.add_argument("--segment", default=r"^FSDP::pre_(?P<pass>forward|backward) \((?P<segment>[^)]*)\)",
                   help="regex of host events opening a segment, with named groups `segment` and `pass`")
    p.add_argument("--layer-type", action="append", default=[], help="REGEX=LABEL on the segment name (repeatable)")
    p.add_argument("--class", dest="classes", action="append", default=[], metavar="LABEL:REGEX",
                   help="class rule on '<host stack> [<dims>] : <kernel name>', checked after nccl (repeatable)")
    p.add_argument("--comm", default="nccl", help="regex (case-insensitive) of communication kernel names")
    p.add_argument("--gemm", default=r"nvjet|xmma|cutlass|gemm|GroupProblemShape|Kernel2|cublas",
                   help="regex (case-insensitive) of GEMM kernel names")
    p.add_argument("--backward-op", default="backward|bwd", help="regex (case-insensitive) of backward custom ops")
    p.add_argument("--recompute-kernels", default=None, help='JSON {"<layer type>": [Inductor kernel names]}')
    p.add_argument("--total-skip", default="nccl", help="comma list of classes left out of the totals")
    p.add_argument("--chain-classes", default="inductor,eager,copy", help="comma list of classes chains may hold")
    p.add_argument("--small-us", type=float, default=50.0, help="chain kernels are shorter than this")
    p.add_argument("--min-chain", type=int, default=2)
    p.add_argument("--hbm-tbps", type=float, default=3.0, help="HBM bandwidth for the fused-pass floor")
    p.add_argument("--top-chains", type=int, default=40)
    p.add_argument("--csv-prefix", default=None)
    return p.parse_args()


def is_custom(name):
    return "::" in name and not name.startswith(TORCH_NAMESPACES) and " " not in name.split("::")[0]


def site(chain, custom):
    if not chain:
        return "<none>"
    op = chain[-1]
    ctx = custom or next((o["name"] for o in reversed(chain[:-1])
                          if not o["name"].startswith(("aten::", "autograd::engine"))), "")
    ctx = re.sub(r"^Torch-Compiled Region: ", "compiled ", ctx)
    return f"{ctx} > {op['name']} {compact_dims(op.get('args', {}).get('Input Dims'))}".strip(" >")


def classify(kernel, chain, context, args, class_rules):
    name = kernel["name"]
    if re.search(args.comm, name, re.I):
        return "nccl"
    target = f"{context} : {name}"
    label = next((lab for lab, rx in class_rules if rx.search(target)), None)
    if label:
        return label
    if re.search(args.gemm, name, re.I) or (chain and GEMM_OP.match(chain[-1]["name"])):
        return "gemm"
    if kernel.get("cat") == "kernel" and any(is_custom(o["name"]) for o in chain):
        return "custom"
    if name.startswith("triton_"):
        return "inductor"
    return "copy" if kernel.get("cat") != "kernel" else "eager"


def kernel_rows(args):
    xs = [e for e in read_trace(args.trace)["traceEvents"] if e.get("ph") == "X"]
    annotations = sorted((e for e in xs if e.get("cat") == "user_annotation"), key=lambda e: e["ts"])
    start = pick([e["ts"] for e in annotations if is_marker(e["name"], args.annotation)], args.annotation_index,
                 f"CPU-side user_annotation `{args.annotation}`")
    end_rx = re.compile(args.end_annotation)
    end = next((e["ts"] for e in annotations if e["ts"] > start and end_rx.search(e["name"])), float("inf"))
    corrs = {e["args"]["correlation"] for e in xs if e.get("cat") in LAUNCH_CATEGORIES
             and "correlation" in e.get("args", {}) and start <= e["ts"] < end}
    gpu = sorted((e for e in xs if e.get("cat") in GPU_CATS and e.get("args", {}).get("correlation") in corrs),
                 key=lambda e: e["ts"])
    stacks = launch_stacks(xs, corrs)
    segments = latest_marks(xs, corrs, re.compile(args.segment))
    layer_types = [(re.compile(spec.split("=", 1)[0]), spec.split("=", 1)[1]) for spec in args.layer_type]
    class_rules = [(spec.split(":", 1)[0], re.compile(spec.split(":", 1)[1])) for spec in args.classes]
    rows = []
    for k in gpu:
        corr = k["args"]["correlation"]
        if corr not in segments:
            continue
        mark, found = segments[corr]
        stack = stacks.get(corr, [])
        chain = [o for o in stack if o.get("cat") == "cpu_op" and o["name"] not in WRAPPER_OPS]
        segment = found.group("segment")
        cls = classify(k, chain, launch_context(stack), args, class_rules)
        custom = next((o["name"] for o in reversed(chain) if is_custom(o["name"])), "")
        rows.append(dict(
            ts=k["ts"], dur=k["dur"], name=k["name"], short=short_name(k["name"]), stream=k["tid"], cls=cls,
            segment=segment, seg_start=mark["ts"], custom=custom, site=site(chain, custom),
            ltype=next((label for rx, label in layer_types if rx.search(segment)), segment),
            pass_="backward" if "backward" in found.group("pass") else "forward",
            compiled=any(o["name"].startswith(COMPILED) for o in stack),
            gemm_dims=json.dumps(chain[-1].get("args", {}).get("Input Dims")) if cls == "gemm" and chain else None,
            bytes=arg_bytes(chain[-1]) if chain else 0,
        ))
    return rows, start, end


def mark_recompute(rows, args):
    recompute_names = defaultdict(set)
    if args.recompute_kernels:
        with open(args.recompute_kernels) as f:
            recompute_names.update((label, set(names)) for label, names in json.load(f).items())
    forward_gemms = defaultdict(set)
    for r in rows:
        if r["pass_"] == "forward" and r["gemm_dims"]:
            forward_gemms[r["ltype"]].add(r["gemm_dims"])
    for r in rows:
        if r["pass_"] != "backward":
            continue
        forward_custom = r["cls"] in ("custom", "gemm") and r["custom"] and not re.search(args.backward_op, r["custom"], re.I)
        forward_gemm = r["cls"] == "gemm" and r["gemm_dims"] in forward_gemms[r["ltype"]]
        listed = r["cls"] == "inductor" and r["name"] in recompute_names[r["ltype"]]
        if forward_custom or forward_gemm or listed:
            r["pass_"] = "recompute"


def inventory(rows, classes, skip, by_pass):
    cells = defaultdict(lambda: [0, 0.0])
    for r in rows:
        key = (r["ltype"], r["pass_"] if by_pass else "all")
        for c in (r["cls"], "total") if r["cls"] not in skip else (r["cls"],):
            cells[key + (c,)][0] += 1
            cells[key + (c,)][1] += r["dur"]
        if not r["compiled"] and r["cls"] not in skip:
            cells[key + ("outside compiled",)][0] += 1
            cells[key + ("outside compiled",)][1] += r["dur"]
    cols = classes + ["total", "outside compiled"]
    lines = ["| layer type | pass | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for key in sorted({c[:2] for c in cells}):
        values = [cells.get(key + (c,), (0, 0.0)) for c in cols]
        lines.append(f"| {key[0]} | {key[1]} | " + " | ".join(f"{n} / {d / 1e3:.2f}" for n, d in values) + " |")
    csv_rows = [dict(layer_type=key[0], pass_=key[1], cls=c, launches=n, ms=round(d / 1e3, 3))
                for (*key, c), (n, d) in sorted(cells.items())]
    return "\n".join(lines), csv_rows


def find_chains(rows, args):
    per_stream = defaultdict(float)
    for r in rows:
        if r["cls"] != "nccl":
            per_stream[r["stream"]] += r["dur"]
    main_stream = max(per_stream, key=per_stream.get)
    small_classes = set(args.chain_classes.split(","))
    chains = defaultdict(lambda: dict(n=0, ms=0.0, launches=0, floor_ms=0.0, sites=None, max_bytes=0, outside=True))

    def label(r):
        return "-" if r is None else r["custom"] or r["short"][:60]

    def flush(run, before, after):
        if len(run) < args.min_chain:
            return
        names = tuple(re.sub(r"_\d+$", "", r["short"]) for r in run)
        c = chains[(run[0]["ltype"], run[0]["pass_"], names, label(before), label(after))]
        biggest = max(r["bytes"] for r in run)
        c["n"] += 1
        c["ms"] += sum(r["dur"] for r in run) / 1e3
        c["launches"] += len(run)
        c["max_bytes"] = max(c["max_bytes"], biggest)
        c["floor_ms"] += biggest / (args.hbm_tbps * 1e12) * 1e3
        c["sites"] = c["sites"] or [r["site"][:140] for r in run]
        c["outside"] = not any(r["compiled"] for r in run)

    run, before = [], None
    for r in sorted((r for r in rows if r["stream"] == main_stream), key=lambda r: r["ts"]):
        small = r["cls"] in small_classes and r["dur"] < args.small_us
        same_invocation = run and all(r[k] == run[0][k] for k in ("segment", "seg_start", "pass_"))
        if small and (not run or same_invocation):
            run.append(r)
            continue
        flush(run, before, r)
        run = [r] if small else []
        if not small:
            before = r
    flush(run, before, None)
    return main_stream, sorted(chains.items(), key=lambda kv: -kv[1]["ms"])


def write_csv(path, rows):
    if rows:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main():
    args = parse_args()
    rows, start, end = kernel_rows(args)
    if not rows:
        sys.exit("no GPU events were launched inside a segment in the window; check --annotation and --segment")
    mark_recompute(rows, args)
    labels = [spec.split(":", 1)[0] for spec in args.classes]
    classes = BUILTIN_CLASSES + [c for c in dict.fromkeys(labels) if c not in BUILTIN_CLASSES] + ["nccl"]
    skip = set(args.total_skip.split(",")) if args.total_skip else set()
    instances = defaultdict(set)
    for r in rows:
        instances[r["ltype"]].add(r["segment"])

    print(f"# Layer inventory: `{args.trace}`\n")
    print(f"- window: launches from CPU `{args.annotation}` [{args.annotation_index}] to the next "
          f"`{args.end_annotation}` ({(end - start) / 1e3:.1f} ms host), {len(rows)} GPU events in segments")
    print("- layer types: " + "; ".join(f"{t}: {', '.join(sorted(s))}" for t, s in sorted(instances.items())))
    print(f"- cells: launches / GPU ms; total skips {', '.join(sorted(skip)) or 'nothing'}")
    by_pass, inventory_csv = inventory(rows, classes, skip, by_pass=True)
    print(f"\n## Per layer type and pass\n\n{by_pass}")
    print(f"\n## Per layer type, all passes\n\n{inventory(rows, classes, skip, by_pass=False)[0]}")

    main_stream, ranked = find_chains(rows, args)
    print(f"\n## Chains of >= {args.min_chain} consecutive small kernels (< {args.small_us:g} us, "
          f"{args.chain_classes}) on stream {main_stream}\n")
    print(f"- {len(ranked)} distinct chains, {sum(c['ms'] for _, c in ranked):.2f} ms in chains\n")
    print("| # | layer type | pass | kernels | n / ms | recoverable ms | before -> after | outside compiled |")
    print("|---|---|---|---|---|---|---|---|")
    for i, ((t, p, names, before, after), c) in enumerate(ranked[: args.top_chains]):
        print(f"| {i} | {t} | {p} | {len(names)} | {c['n']} / {c['ms']:.2f} | {c['ms'] - c['floor_ms']:.2f} |"
              f" {before} -> {after} | {'yes' if c['outside'] else 'no'} |")
    print()
    for i, ((t, p, names, before, after), c) in enumerate(ranked[: args.top_chains]):
        print(f"{i}. {t} {p} ({c['n']}x, {c['ms']:.2f} ms, max kernel bytes {c['max_bytes'] / 1e6:.1f} MB):")
        for name, s in zip(names, c["sites"]):
            print(f"   - {name[:110]}  @ {s}")

    if args.csv_prefix:
        write_csv(f"{args.csv_prefix}_inventory.csv", inventory_csv)
        write_csv(f"{args.csv_prefix}_chains.csv", [
            dict(layer_type=t, pass_=p, kernels=" | ".join(names), before=before, after=after, occurrences=c["n"],
                 ms_per_step=round(c["ms"], 3), floor_ms=round(c["floor_ms"], 3),
                 recoverable_ms=round(c["ms"] - c["floor_ms"], 3), outside_compiled=c["outside"],
                 sites=" | ".join(c["sites"]))
            for (t, p, names, before, after), c in ranked])
        write_csv(f"{args.csv_prefix}_kernels.csv", [
            {"ts": r["ts"], "dur_us": r["dur"], "stream": r["stream"], "layer_type": r["ltype"],
             "segment": r["segment"], "pass": r["pass_"], "class": r["cls"], "compiled": r["compiled"],
             "bytes": r["bytes"], "kernel": r["name"][:200], "site": r["site"][:200]}
            for r in rows])


if __name__ == "__main__":
    main()
