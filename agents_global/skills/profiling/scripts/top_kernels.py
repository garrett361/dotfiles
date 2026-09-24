"""Print markdown tables of the most expensive GPU kernels in a window of a torch.profiler chrome trace.

The default window runs from the last CPU-side `user_annotation` named `forward` (prime-rl SFT's per-step
marker, as in `trim_last_step.py`) to the last GPU event end. Kernels, memcpys, and memsets that start in the
window are grouped by kernel name, by call site (innermost `cpu_op` with its `Input Dims`, plus the nearest
enclosing non-aten op, found via `args["correlation"]` -> launch -> enclosing ops on the launch thread), or by
both. Ranks by total time and by time per call; NCCL kernels get their own table.

Usage: python3 top_kernels.py <trace.json.gz> [--by name|site|both] [--top 15] [--stream main|<tid>]
         [--annotation forward | --whole-trace] [--min-calls 1] [--minmax] [--name-width 55] [--csv out.csv]
"""

import argparse
import csv
import gzip
import json
import re
import statistics
import textwrap
from collections import defaultdict

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


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("trace")
    p.add_argument("--by", choices=("name", "site", "both"), default="name")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--stream", default=None, help="'main' (most kernel time) or a stream tid")
    p.add_argument("--annotation", default="forward")
    p.add_argument("--whole-trace", action="store_true")
    p.add_argument("--min-calls", type=int, default=1, help="minimum launches for the per-call ranking")
    p.add_argument("--minmax", action="store_true")
    p.add_argument("--name-width", type=int, default=55)
    p.add_argument("--csv", default=None)
    return p.parse_args()


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


def call_sites(xs, kernels):
    wanted = {k["args"].get("correlation") for k in kernels}
    launches = [e for e in xs if e.get("cat") in LAUNCH_CATS and e.get("args", {}).get("correlation") in wanted]
    launch_tids = {e["tid"] for e in launches}
    ops_by_tid, launches_by_tid = defaultdict(list), defaultdict(list)
    for e in xs:
        if e.get("cat") == "cpu_op" and e["tid"] in launch_tids and e["name"] not in WRAPPER_OPS:
            ops_by_tid[e["tid"]].append(e)
    for e in launches:
        launches_by_tid[e["tid"]].append(e)
    site_by_corr = {}
    for tid, tid_launches in launches_by_tid.items():
        ops = sorted(ops_by_tid[tid], key=lambda e: (e["ts"], -e["dur"]))
        stack, i = [], 0
        for launch in sorted(tid_launches, key=lambda e: e["ts"]):
            while i < len(ops) and ops[i]["ts"] <= launch["ts"]:
                while stack and stack[-1]["ts"] + stack[-1]["dur"] < ops[i]["ts"]:
                    stack.pop()
                stack.append(ops[i])
                i += 1
            chain = [o for o in stack if o["ts"] + o["dur"] >= launch["ts"]]
            site_by_corr[launch["args"]["correlation"]] = describe_site(chain)
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
            f"{r['total_us'] / 1e3:8.1f}",
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


def main():
    args = parse_args()
    events = json.load(gzip.open(args.trace))["traceEvents"]
    xs = [e for e in events if e.get("ph") == "X"]
    gpu = [e for e in xs if e.get("cat") in GPU_CATS]
    end = max(e["ts"] + e["dur"] for e in gpu)
    if args.whole_trace:
        start = min(e["ts"] for e in gpu)
    else:
        start = max(e["ts"] for e in xs if e.get("cat") == "user_annotation" and e.get("name") == args.annotation)
    gpu = [e for e in gpu if e["ts"] >= start]
    stream_time = defaultdict(float)
    for e in gpu:
        stream_time[e["tid"]] += e["dur"]
    if args.stream == "main":
        main_stream = max(stream_time, key=stream_time.get)
        gpu = [e for e in gpu if e["tid"] == main_stream]
    elif args.stream is not None:
        gpu = [e for e in gpu if str(e["tid"]) == args.stream]
    window = end - start
    busy = union_length((e["ts"], e["ts"] + e["dur"]) for e in gpu)
    compute_busy = union_length((e["ts"], e["ts"] + e["dur"]) for e in gpu if not is_comm(e["name"]))
    sites = call_sites(xs, gpu) if args.by in ("site", "both") else {}

    def key_of(e):
        site = sites.get(e["args"].get("correlation"), "<no launch event>")
        return (None if args.by == "name" else site, None if args.by == "site" else e["name"])

    groups = {False: defaultdict(list), True: defaultdict(list)}
    full_names = defaultdict(set)
    for e in gpu:
        key = key_of(e)
        groups[is_comm(e["name"])][key].append(e["dur"])
        full_names[key].add(e["name"])
    compute, comm = summarize(groups[False]), summarize(groups[True])
    labels = make_labels({r["key"] for r in compute + comm})

    streams = ", ".join(f"{tid}: {t / 1e3:.1f}" for tid, t in sorted(stream_time.items(), key=lambda kv: -kv[1])[:5])
    print(f"# Top GPU kernels: `{args.trace}`\n")
    print(f"- window: {window / 1e3:.1f} ms ({'whole trace' if args.whole_trace else f'last `{args.annotation}` to last GPU event'})"
          f", stream filter: {args.stream or 'none'}, grouped by {args.by}")
    print(f"- GPU busy (union over selected streams): {busy / 1e3:.1f} ms ({100 * busy / window:.1f}% of window);"
          f" non-NCCL busy {compute_busy / 1e3:.1f} ms")
    print(f"- summed durations: non-NCCL {sum(r['total_us'] for r in compute) / 1e3:.1f} ms,"
          f" NCCL {sum(r['total_us'] for r in comm) / 1e3:.1f} ms; {len(gpu)} GPU events")
    print(f"- kernel ms per stream (all streams, in window): {streams}\n")
    print(f"## Non-NCCL, by total time (top {args.top})\n")
    print(table(sorted(compute, key=lambda r: -r["total_us"])[: args.top], busy, window, labels, args))
    print(f"\n## Non-NCCL, by time per call (top {args.top}, calls >= {args.min_calls})\n")
    per_call = [r for r in compute if r["calls"] >= args.min_calls]
    print(table(sorted(per_call, key=lambda r: -r["mean_us"])[: args.top], busy, window, labels, args))
    print("\n## NCCL (durations include waiting for peers)\n")
    print(table(sorted(comm, key=lambda r: -r["total_us"])[: args.top], busy, window, labels, args))
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
                             "min_us", "max_us", "kernel_names"])
            for group, rows in (("compute", compute), ("nccl", comm)):
                for r in sorted(rows, key=lambda r: -r["total_us"]):
                    writer.writerow([group, labels[r["key"]], f"{r['total_us']:.3f}", f"{100 * r['total_us'] / busy:.2f}",
                                     f"{100 * r['total_us'] / window:.2f}", r["calls"], f"{r['mean_us']:.3f}",
                                     f"{r['median_us']:.3f}", f"{r['min_us']:.3f}", f"{r['max_us']:.3f}",
                                     " || ".join(sorted(full_names[r["key"]]))])


main()
