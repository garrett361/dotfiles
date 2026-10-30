# /// script
# requires-python = ">=3.10"
# ///
"""Print markdown tables of the most expensive GPU kernels in a window of a torch.profiler chrome trace.

The default window runs from the last CPU-side `user_annotation` named `forward` (as in `trim_last_step.py`) to the
last GPU event end. prime-rl wraps each micro-batch's forward in `forward`, so with K micro-batches per step the
default covers only the last micro-batch; `--annotation-index -K --annotation-span K` covers the last step. Kernels, memcpys, and memsets that start in the
window are grouped by kernel name, by call site (innermost `cpu_op` with its `Input Dims`, plus the nearest
enclosing non-aten op, found via `args["correlation"]` -> launch -> enclosing ops on the launch thread), or by
both. Ranks by total time and by time per call; NCCL kernels get their own table.

Every annotation name also matches `NAME#<n>`: for a loop driven by `torch.profiler.schedule` and `prof.step()`, pass
`ProfilerStep` to window on torch's per-step `ProfilerStep#<n>` ranges. CPU-side windows select kernels by GPU start
time, so when the host runs ahead of the GPU they misplace kernels; there, `--from-annotation ProfilerStep
--from-index -2 --to-annotation ProfilerStep` (GPU-side) or `--launched-in ProfilerStep` gives the real step. The
trace may be `.json` or `.json.gz`.

`--annotation-index N` starts the window at the Nth such annotation instead (0-based, negative from the end); unless
it is the last one, the window ends at the next one's start, so `--annotation-index -3` covers the third-to-last
step. `--from-annotation NAME` instead windows on GPU-side `record_function` projections (`gpu_user_annotation`):
from the start of the `--from-index`th one named NAME to the start of the first later one named `--to-annotation`
(default: the end of the opening one), e.g. one decoder layer's forward, or its recompute plus backward.
`--launched-in NAME` keeps only kernels launched (via `args["correlation"]`) inside the `--launched-in-index`th CPU-side
`user_annotation` named NAME, for host ranges torch does not project onto the GPU (e.g. prime-rl's `optimizer`); the
window runs from the first such kernel's start to the last one's end.

`--annotation-span N` ends an `--annotation` window at the Nth later annotation instead of the next one, for loops that
annotate each micro-batch (e.g. prime-rl RL's `forward` with 2 micro-batches per step: `--annotation-index -4
--annotation-span 2` is the second-to-last whole step). `--category LABEL:REGEX` (repeatable, first match wins on the raw
kernel name, unmatched kernels go to "other") adds a per-category table with summed and union time.

`--marker REGEX` (site grouping only) prefixes each call site with `[M]`, where M is the most recent host event
(`cpu_op` or `user_annotation`) on the launch's thread that started at or before the launch and whose name matches
REGEX (its first capture group if it has one), or `[-]` if none did. It splits rows by layer or phase, e.g. prime-rl's
FSDP2 hooks, which fire on the forward thread and on autograd's thread:
`--marker 'FSDP::(?:pre_forward|pre_backward) \\((model\\.layers\\.\\d+|model\\.norm, lm_head|model\\.embed_tokens)\\)|(Optimizer\\.step)'`.
`--arg-bytes` adds a CSV column `site_arg_bytes`: the median over a row's launches of the bytes spanned by the
launching op's tensor arguments (`Input Dims`, `Input Strides`, `Input type`). A stride-0 broadcast counts once, and
lists and unknown dtypes count zero. Inductor's Triton launches record every buffer, outputs included, so for them it
approximates the kernel's traffic. An `aten::` op records only its inputs (and `out=`/in-place targets). A custom op
that launches several kernels reports its whole argument list on each.

The header reports GPU busy time (union of kernel intervals on all selected streams, clipped to the window end), idle time (window minus busy),
and exposed NCCL time (when an NCCL kernel runs and no non-NCCL kernel does, i.e. busy minus non-NCCL busy).

Usage: uv run --script top_kernels.py <trace.json.gz> [--by name|site|both] [--top 15] [--stream main|<tid>]
         [--annotation forward [--annotation-index -1] | --whole-trace | --from-annotation NAME [--from-index -1]
          [--to-annotation NAME] | --launched-in NAME [--launched-in-index -1]] [--min-calls 1] [--minmax] [--name-width 55] [--csv out.csv]
         [--decimals 1] [--marker REGEX] [--arg-bytes]
  e.g. layer 12's recompute and backward in the last step of a prime-rl SFT trace:
    --from-annotation "FSDP::all_gather_copy_out (model.layers.12) [pg=16]" --from-index -1 \\
    --to-annotation "FSDP::all_gather_copy_out (model.layers.11) [pg=16]"
"""

import argparse
import bisect
import csv
import json
import math
import re
import statistics
import sys
import textwrap
from collections import defaultdict

from trace_events import is_marker, pick, read_trace

GPU_CATS = ("kernel", "gpu_memcpy", "gpu_memset")
LAUNCH_CATS = ("cuda_runtime", "cuda_driver")
WRAPPER_OPS = ("PythonDispatchMode", "PythonSubclass", "detach")
NAME_REWRITES = [
    (r"\b(at::native::|at::cuda::detail::|at::cuda::|at::|c10::|std::|binary_internal::|detail::)", ""),
    (r"::operator\(\)\(\) const", ""),
    (r"\{lambda\(\)#\d+\}::", ""),
    (r"\{lambda\(([^()]*)\)#\d+\}", r"lambda(\1)"),
    (r", array<char\*, \d+ul>\s*", ""),
    (r"func_wrapper_t<\w+, (\w+)<[^<>]*>::operator\(\)::lambda\([^()]*\)>", r"\1"),
    (r"gpu_kernel_impl(_nocast)?<", ""),
    (r"BinaryFunctor<(\w+), [^<>]*?, (\w+Functor<)", r"BinaryFunctor<\1, \2"),
    (r"\s*>*\s*::lambda\(int\)", ""),
    (r", (TrivialOffsetCalculator<\d+, unsigned int>|memory::\w+<\d+>)", ""),
    (r"\s+", " "),
    (r"\s+>", ">"),
]
CONTEXT_REWRITES = [
    (r"^GeneratedBackwardFor_(\w+?)_defaultBackward$", r"\1 (bwd)"),
    (r"^GeneratedBackwardFor_(\w+?)_default$", r"\1"),
    (r"^Torch-Compiled Region: ", "compiled "),
]
MANGLED_STOPWORDS = {
    "at", "cuda", "detail", "cute", "tuple", "gemm", "kernel", "collective", "C", "Params", "device_kernel", "Layout",
    "Underscore", "identity", "epilogue", "fusion", "enable_3x_kernel_for_sm10", "CollectiveMma", "TiledMMA",
    "MMA_Atom", "UMMA", "Major", "E", "ScaleIn",
}
DTYPE_BYTES = {
    "double": 8, "float": 4, "c10::Half": 2, "c10::BFloat16": 2, "c10::Float8_e4m3fn": 1, "c10::Float8_e4m3fnuz": 1,
    "c10::Float8_e5m2": 1, "c10::Float8_e5m2fnuz": 1, "c10::Float8_e8m0fnu": 1, "long int": 8, "int": 4,
    "short int": 2, "signed char": 1, "unsigned char": 1, "bool": 1, "c10::complex<float>": 8,
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("trace")
    p.add_argument("--by", choices=("name", "site", "both"), default="name")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--stream", default=None, help="'main' (most kernel time) or a stream tid")
    p.add_argument("--annotation", default="forward")
    p.add_argument("--annotation-index", type=int, default=-1, help="which step annotation opens the window")
    p.add_argument("--from-annotation", default=None, help="GPU-side annotation name opening the window")
    p.add_argument("--from-index", type=int, default=-1, help="which occurrence of --from-annotation")
    p.add_argument("--to-annotation", default=None, help="first later GPU-side annotation with this name closes it")
    p.add_argument("--launched-in", default=None,
                   help="CPU-side user_annotation name: keep kernels launched inside its --launched-in-index'th range")
    p.add_argument("--launched-in-index", type=int, default=-1, help="which occurrence of --launched-in")
    p.add_argument("--whole-trace", action="store_true")
    p.add_argument("--min-calls", type=int, default=1, help="minimum launches for the per-call ranking")
    p.add_argument("--minmax", action="store_true")
    p.add_argument("--name-width", type=int, default=55)
    p.add_argument("--csv", default=None)
    p.add_argument("--category", action="append", default=[], metavar="LABEL:REGEX",
                   help="ordered rules matched against raw kernel names; adds a per-category table (repeatable)")
    p.add_argument("--decimals", type=int, default=1, help="decimal places for ms totals (e.g. 3 for op-level traces)")
    p.add_argument("--annotation-span", type=int, default=1,
                   help="with --annotation: end the window at the Nth later step annotation instead of the next one")
    p.add_argument("--marker", default=None,
                   help="prefix sites with the most recent matching host event on the launch thread")
    p.add_argument("--arg-bytes", action="store_true",
                   help="add the CSV column site_arg_bytes (bytes spanned by the launching op's tensor arguments)")
    return p.parse_args()


def arg_bytes(op):
    args = op.get("args", {})
    total = 0
    for dims, strides, dtype in zip(args.get("Input Dims", []), args.get("Input Strides", []), args.get("Input type", [])):
        size = DTYPE_BYTES.get(dtype)
        if size is None or not isinstance(dims, list) or not all(isinstance(d, int) for d in dims):
            continue
        if any(d == 0 for d in dims):
            continue
        if isinstance(strides, list) and len(strides) == len(dims) and all(isinstance(s, int) for s in strides):
            extent = 1 + sum((d - 1) * s for d, s in zip(dims, strides) if s > 0)
            elements = min(extent, math.prod(dims))
        else:
            elements = math.prod(dims)
        total += elements * size
    return total


def strip_params(name):
    depth = 0
    for i, ch in enumerate(name):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "(" and depth == 0 and i > 0:
            return name[:i]
    return name


def drop_reference_arglists(name):
    out, i = [], 0
    while i < len(name):
        if name[i] == "(":
            depth, j = 1, i + 1
            while j < len(name) and depth:
                depth += {"(": 1, ")": -1}.get(name[j], 0)
                j += 1
            if "&" in name[i:j]:
                i = j
                continue
        out.append(name[i])
        i += 1
    return "".join(out)


def mangled_identifiers(name):
    found, i = [], 2
    while i < len(name):
        digits = re.match(r"\d+", name[i:])
        if digits is None:
            i += 1
            continue
        j = i + len(digits.group())
        ident = name[j : j + int(digits.group())]
        if name[i - 1] not in "SiT" and re.fullmatch(r"[A-Za-z_]\w*", ident):
            if ident not in MANGLED_STOPWORDS and ident not in found:
                found.append(ident)
            i = j + len(ident)
        else:
            i = j
    return " ".join(found[:8])


def short_name(name):
    if name.startswith(("Memcpy ", "Memset ")):
        return name
    if name.startswith("_Z"):
        return mangled_identifiers(name)
    name = strip_params(re.sub(r"\(anonymous namespace\)::", "", name.removeprefix("void ")))
    name = drop_reference_arglists(name)
    for pattern, repl in NAME_REWRITES:
        name = re.sub(pattern, repl, name).strip()
    unclosed = name.count("<") - name.count(">")
    while unclosed < 0 and name.endswith(">"):
        name, unclosed = name[:-1].rstrip(), unclosed + 1
    return name + ">" * max(unclosed, 0)


def compact_dims(dims):
    if not dims:
        return ""
    shapes = [json.dumps(d, separators=(",", ":")) for d in dims if d not in ([], None, "")]
    return ",".join(shapes[:3]) + (",..." if len(shapes) > 3 else "")


def union_length(intervals):
    total, cur_start, cur_end = 0.0, None, None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    return total + (cur_end - cur_start if cur_end is not None else 0.0)


def call_sites(xs, kernels, marker=None, bytes_out=None):
    """Map each kernel's correlation id to its site label, and fill `bytes_out` (if given) with arg_bytes."""
    wanted = {k["args"].get("correlation") for k in kernels}
    launches = [e for e in xs if e.get("cat") in LAUNCH_CATS and e.get("args", {}).get("correlation") in wanted]
    launch_tids = {e["tid"] for e in launches}
    ops_by_tid, launches_by_tid, marks_by_tid = defaultdict(list), defaultdict(list), defaultdict(list)
    marker_rx = re.compile(marker) if marker else None
    for e in xs:
        if e.get("cat") == "cpu_op" and e["tid"] in launch_tids and e["name"] not in WRAPPER_OPS:
            ops_by_tid[e["tid"]].append(e)
        if marker_rx and e.get("cat") in ("cpu_op", "user_annotation") and e["tid"] in launch_tids:
            found = marker_rx.search(e["name"])
            if found:
                text = next((g for g in found.groups() if g is not None), found.group(0))
                marks_by_tid[e["tid"]].append((e["ts"], text))
    for e in launches:
        launches_by_tid[e["tid"]].append(e)
    site_by_corr = {}
    for tid, tid_launches in launches_by_tid.items():
        ops = sorted(ops_by_tid[tid], key=lambda e: (e["ts"], -e["dur"]))
        marks = sorted(marks_by_tid[tid])
        mark_times = [t for t, _ in marks]
        stack, i = [], 0
        for launch in sorted(tid_launches, key=lambda e: e["ts"]):
            while i < len(ops) and ops[i]["ts"] <= launch["ts"]:
                while stack and stack[-1]["ts"] + stack[-1]["dur"] < ops[i]["ts"]:
                    stack.pop()
                stack.append(ops[i])
                i += 1
            chain = [o for o in stack if o["ts"] + o["dur"] >= launch["ts"]]
            site = describe_site(chain)
            if marker_rx:
                j = bisect.bisect_right(mark_times, launch["ts"]) - 1
                site = f"[{marks[j][1] if j >= 0 else '-'}] {site}"
            site_by_corr[launch["args"]["correlation"]] = site
            if bytes_out is not None:
                bytes_out[launch["args"]["correlation"]] = arg_bytes(chain[-1]) if chain else 0
    return site_by_corr


def rename_context(name):
    for pattern, repl in CONTEXT_REWRITES:
        name = re.sub(pattern, repl, name)
    return name


def describe_site(chain):
    if not chain:
        return "<no enclosing cpu_op>"
    op = chain[-1]
    dims = compact_dims(op.get("args", {}).get("Input Dims"))
    name = op["name"]
    if name == "record_param_comms":
        callers = [o["name"] for o in reversed(chain[:-1])]
        name = rename_context(next((n for n in callers if not n.startswith("c10d::")), callers[0] if callers else name))
    site = f"{name} {dims}".strip()
    if not op["name"].startswith("aten::"):
        return site
    outer = [o["name"] for o in chain[:-1] if o["name"] != op["name"]]
    ctx = next((n for n in reversed(outer) if not n.startswith(("aten::", "autograd::engine"))), outer[0] if outer else "")
    ctx = rename_context(ctx)
    return f"{ctx} > {site}" if ctx else site


def is_comm(name):
    return "nccl" in name.lower()


def summarize(groups):
    rows = []
    for key, durs in groups.items():
        rows.append(
            {
                "key": key,
                "total_us": sum(durs),
                "calls": len(durs),
                "mean_us": statistics.fmean(durs),
                "median_us": statistics.median(durs),
                "min_us": min(durs),
                "max_us": max(durs),
            }
        )
    return rows


def table(rows, busy, window, labels, args):
    cols = [" #", "total ms", "% busy", "% win", "calls", "mean ms", " med ms"]
    if args.minmax:
        cols += [" min ms", " max ms"]
    lines = ["| " + " | ".join(cols) + " | " + "name".ljust(args.name_width) + " |"]
    lines.append("|" + "|".join("-" * (len(c) + 2) for c in cols) + "|" + "-" * (args.name_width + 2) + "|")
    footnotes = []
    for rank, r in enumerate(rows, 1):
        vals = [
            f"{rank:>1}",
            f"{r['total_us'] / 1e3:8.{args.decimals}f}",
            f"{100 * r['total_us'] / busy:6.1f}",
            f"{100 * r['total_us'] / window:5.1f}",
            f"{r['calls']:5d}",
            f"{r['mean_us'] / 1e3:7.3f}",
            f"{r['median_us'] / 1e3:6.3f}",
        ]
        if args.minmax:
            vals += [f"{r['min_us'] / 1e3:6.3f}", f"{r['max_us'] / 1e3:6.3f}"]
        label = labels[r["key"]]
        if len(label) > args.name_width:
            footnotes.append(f"- {rank}: `{label if len(label) <= 160 else label[:157] + '...'}`")
            label = label[: args.name_width - 3] + "..."
        lines.append("| " + " | ".join(v.rjust(len(c)) for v, c in zip(vals, cols)) + " | " + label.ljust(args.name_width) + " |")
    return "\n".join(lines + ([""] + footnotes if footnotes else []))


def display(key):
    site, name = key
    if name is None:
        return site
    return short_name(name) if site is None else f"{site} : {short_name(name)}"


def make_labels(keys):
    labels, seen = {}, defaultdict(int)
    for key in sorted(keys, key=lambda k: (display(k), k[0] or "", k[1] or "")):
        text = display(key)
        seen[text] += 1
        labels[key] = text if seen[text] == 1 else f"{text} #{seen[text]}"
    return labels


def category_table(gpu, end, busy, window, specs, d=1):
    rules = [(label, re.compile(regex)) for label, regex in (spec.split(":", 1) for spec in specs)]
    durs, intervals = defaultdict(list), defaultdict(list)
    for e in gpu:
        label = next((lab for lab, rx in rules if rx.search(e["name"])), "other")
        durs[label].append(e["dur"])
        intervals[label].append((e["ts"], min(e["ts"] + e["dur"], end)))
    lines = ["\n## By category (first matching `--category` rule on the raw kernel name)\n",
             "| category | total ms | union ms | % busy | % win | calls |", "|---|---|---|---|---|---|"]
    for label in [lab for lab, _ in rules] + ["other"]:
        if label not in durs:
            continue
        total = sum(durs[label])
        lines.append(f"| {label} | {total / 1e3:.{d}f} | {union_length(intervals[label]) / 1e3:.{d}f} |"
                     f" {100 * total / busy:.1f} | {100 * total / window:.1f} | {len(durs[label])} |")
    lines.append("\nunion ms = time covered by at least one kernel of the category (overlap across streams counted once).")
    return "\n".join(lines)


def main():
    args = parse_args()
    events = read_trace(args.trace)["traceEvents"]
    xs = [e for e in events if e.get("ph") == "X"]
    gpu = [e for e in xs if e.get("cat") in GPU_CATS]
    if not gpu:
        sys.exit("no kernel, gpu_memcpy or gpu_memset events in the trace (captured without ProfilerActivity.CUDA?)")
    end = max(e["ts"] + e["dur"] for e in gpu)
    if args.whole_trace:
        start = min(e["ts"] for e in gpu)
        description = "whole trace"
    elif args.launched_in:
        ranges = sorted((e for e in xs if e.get("cat") == "user_annotation" and is_marker(e["name"], args.launched_in)),
                        key=lambda e: e["ts"])
        host = pick(ranges, args.launched_in_index, f"CPU-side user_annotation `{args.launched_in}`")
        launched = {e["args"]["correlation"] for e in xs if e.get("cat") in ("cuda_runtime", "cuda_driver")
                    and "correlation" in e.get("args", {}) and host["ts"] <= e["ts"] < host["ts"] + host["dur"]}
        gpu = [e for e in gpu if e.get("args", {}).get("correlation") in launched]
        if not gpu:
            sys.exit(f"no GPU events were launched inside CPU `{args.launched_in}` [{args.launched_in_index}]")
        start, end = min(e["ts"] for e in gpu), max(e["ts"] + e["dur"] for e in gpu)
        description = (f"kernels launched in CPU `{args.launched_in}` [{args.launched_in_index}],"
                       " from the first one's start to the last one's end")
    elif args.from_annotation:
        marks = sorted((e for e in xs if e.get("cat") == "gpu_user_annotation"), key=lambda e: e["ts"])
        opener = pick([e for e in marks if is_marker(e["name"], args.from_annotation)], args.from_index,
                      f"GPU-side annotation `{args.from_annotation}`")
        start, end = opener["ts"], opener["ts"] + opener["dur"]
        if args.to_annotation:
            closers = [e["ts"] for e in marks if is_marker(e["name"], args.to_annotation) and e["ts"] > start]
            end = pick(closers, 0, f"GPU-side annotation `{args.to_annotation}` after the opening one")
        description = f"GPU `{args.from_annotation}` [{args.from_index}] to " + (
            f"next GPU `{args.to_annotation}`" if args.to_annotation else "its end")
    else:
        steps = sorted(e["ts"] for e in xs
                       if e.get("cat") == "user_annotation" and is_marker(e["name"], args.annotation))
        start = pick(steps, args.annotation_index,
                     f"CPU-side user_annotation `{args.annotation}` (or `{args.annotation}#<n>`)")
        later = [t for t in steps if t > start]
        if len(later) >= args.annotation_span:
            end = later[args.annotation_span - 1]
        description = (f"`{args.annotation}` [{args.annotation_index}] to "
                       + (f"{args.annotation_span} annotation(s) later" if len(later) >= args.annotation_span
                          else "last GPU event"))
    gpu = [e for e in gpu if start <= e["ts"] < end]
    if not gpu:
        sys.exit(f"no GPU events start in the window ({description})")
    stream_time = defaultdict(float)
    for e in gpu:
        stream_time[e["tid"]] += e["dur"]
    if args.stream == "main":
        main_stream = max(stream_time, key=stream_time.get)
        gpu = [e for e in gpu if e["tid"] == main_stream]
    elif args.stream is not None:
        gpu = [e for e in gpu if str(e["tid"]) == args.stream]
    window = end - start
    busy = union_length((e["ts"], min(e["ts"] + e["dur"], end)) for e in gpu)
    compute_busy = union_length((e["ts"], min(e["ts"] + e["dur"], end)) for e in gpu if not is_comm(e["name"]))
    site_bytes = {}
    sites = call_sites(xs, gpu, args.marker, site_bytes) if args.by in ("site", "both") else {}

    def key_of(e):
        site = sites.get(e["args"].get("correlation"), "<no launch event>")
        return (None if args.by == "name" else site, None if args.by == "site" else e["name"])

    groups = {False: defaultdict(list), True: defaultdict(list)}
    full_names = defaultdict(set)
    bytes_by_key = defaultdict(list)
    for e in gpu:
        key = key_of(e)
        groups[is_comm(e["name"])][key].append(e["dur"])
        full_names[key].add(e["name"])
        bytes_by_key[key].append(site_bytes.get(e["args"].get("correlation"), 0))
    compute, comm = summarize(groups[False]), summarize(groups[True])
    labels = make_labels({r["key"] for r in compute + comm})

    d = args.decimals
    streams = ", ".join(f"{tid}: {t / 1e3:.{d}f}" for tid, t in sorted(stream_time.items(), key=lambda kv: -kv[1])[:5])
    print(f"# Top GPU kernels: `{args.trace}`\n")
    print(f"- window: {window / 1e3:.{d}f} ms ({description})"
          f", stream filter: {args.stream or 'none'}, grouped by {args.by}")
    print(f"- GPU busy (union over selected streams): {busy / 1e3:.{d}f} ms ({100 * busy / window:.1f}% of window);"
          f" non-NCCL busy {compute_busy / 1e3:.{d}f} ms ({100 * compute_busy / window:.1f}%)")
    print(f"- GPU idle: {(window - busy) / 1e3:.{d}f} ms ({100 * (window - busy) / window:.1f}%); exposed NCCL (no"
          f" non-NCCL kernel running): {(busy - compute_busy) / 1e3:.{d}f} ms ({100 * (busy - compute_busy) / window:.1f}%)")
    print(f"- summed durations: non-NCCL {sum(r['total_us'] for r in compute) / 1e3:.{d}f} ms,"
          f" NCCL {sum(r['total_us'] for r in comm) / 1e3:.{d}f} ms; {len(gpu)} GPU events")
    print(f"- kernel ms per stream (all streams, in window): {streams}\n")
    print(f"## Non-NCCL, by total time (top {args.top})\n")
    print(table(sorted(compute, key=lambda r: -r["total_us"])[: args.top], busy, window, labels, args))
    print(f"\n## Non-NCCL, by time per call (top {args.top}, calls >= {args.min_calls})\n")
    per_call = [r for r in compute if r["calls"] >= args.min_calls]
    print(table(sorted(per_call, key=lambda r: -r["mean_us"])[: args.top], busy, window, labels, args))
    print("\n## NCCL (durations include waiting for peers)\n")
    print(table(sorted(comm, key=lambda r: -r["total_us"])[: args.top], busy, window, labels, args))
    if args.category:
        print(category_table(gpu, end, busy, window, args.category, d))
    print()
    print(textwrap.fill(
        "Legend: total = summed durations in the window; % busy = total / GPU busy time and % win = total /"
        " window (shares can sum past 100 when streams overlap); calls = launches; mean/med = per launch."
        " Names drop namespaces, lambdas, and argument lists (mangled names list their first identifiers);"
        " `#n` separates distinct kernels that shorten alike; truncated labels are listed under each table by"
        " rank; raw names are in the CSV. Site = `[<nearest non-aten enclosing op> >] <innermost cpu_op>"
        " <first 3 Input Dims>`; a site can launch several kernels, so its mean/median mix them.",
        width=115,
    ))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["group", "label", "total_us", "pct_busy", "pct_window", "calls", "mean_us", "median_us",
                             "min_us", "max_us", "kernel_names"] + (["site_arg_bytes"] if args.arg_bytes else []))
            for group, rows in (("compute", compute), ("nccl", comm)):
                for r in sorted(rows, key=lambda r: -r["total_us"]):
                    extra = [f"{statistics.median(bytes_by_key[r['key']]):.0f}"] if args.arg_bytes else []
                    writer.writerow([group, labels[r["key"]], f"{r['total_us']:.3f}", f"{100 * r['total_us'] / busy:.2f}",
                                     f"{100 * r['total_us'] / window:.2f}", r["calls"], f"{r['mean_us']:.3f}",
                                     f"{r['median_us']:.3f}", f"{r['min_us']:.3f}", f"{r['max_us']:.3f}",
                                     " || ".join(sorted(full_names[r["key"]]))] + extra)


if __name__ == "__main__":
    main()
