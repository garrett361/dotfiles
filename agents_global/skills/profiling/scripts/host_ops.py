# /// script
# requires-python = ">=3.10"
# ///
"""Host-side cost per training step from torch.profiler traces: launches, thread busy time, and named op groups.

Step windows are host-side: from the launch call of the last kernel in one cluster of `--step-boundary` kernels
(e.g. the optimizer's) to the launch of the last kernel in the next cluster, so they line up with the GPU-side
windows of step_accounting.py. Per arm (averaged over the selected steps and over ranks), it prints:
- per host thread with CUDA calls: kernel and memcpy/memset launch calls per step, host time inside those calls,
  and busy time (union of the thread's cpu_op and user_annotation ranges);
- for each `--op LABEL:REGEX` group (repeatable, matched on cpu_op names, outermost match only): calls, inclusive
  host time, and launch calls issued inside per step.
With two arms a delta column is added. Tracing inflates host time (every op and launch is recorded), so read the
host times as relative costs between arms, and the launch counts as exact.

Usage:
  uv run --script host_ops.py --trace "bf16=traces/bf16/trace_*.json.gz" --trace "fp8=traces/fp8/trace_*.json.gz" \\
    --step-boundary FusedAdamMathFunctor --steps=-2: --op "FP8 expert GEMM:^prime_rl::grouped_fp8_gemm" \\
    --op "bf16 grouped mm:^aten::_grouped_mm" [--ranks 0,4]
"""

import argparse
import glob
import gzip
import json
import re
from collections import defaultdict

LAUNCH = re.compile(r"LaunchKernel|cuLaunch|MemcpyAsync|MemsetAsync|cuMemcpy|cuMemset")


def load(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return [e for e in json.load(f)["traceEvents"] if e.get("ph") == "X"]


def windows(events, boundary, gap_us):
    launches = {e["args"]["correlation"]: e for e in events
                if e.get("cat") in ("cuda_runtime", "cuda_driver") and "correlation" in e.get("args", {})}
    marks = sorted((e["ts"], e["ts"] + e["dur"], launches.get(e.get("args", {}).get("correlation")))
                   for e in events if e.get("cat") == "kernel" and boundary.search(e["name"]))
    cluster_last = [m for m, nxt in zip(marks, marks[1:] + [(float("inf"), 0, None)]) if nxt[0] - m[1] > gap_us]
    host_marks = [m[2]["ts"] for m in cluster_last if m[2] is not None]
    return list(zip(host_marks[:-1], host_marks[1:]))


def union(intervals):
    total, end = 0.0, float("-inf")
    for s, e in sorted(intervals):
        if e <= end:
            continue
        total += e - max(s, end)
        end = e
    return total


def analyze(events, lo, hi, ops):
    by_thread = defaultdict(list)
    for e in events:
        if e.get("cat") in ("cpu_op", "user_annotation", "cuda_runtime", "cuda_driver") and lo <= e["ts"] < hi:
            by_thread[e["tid"]].append(e)
    threads, groups = {}, defaultdict(lambda: [0, 0.0, 0])
    for tid, evs in by_thread.items():
        calls = [e for e in evs if e.get("cat") in ("cuda_runtime", "cuda_driver") and LAUNCH.search(e["name"])]
        if not calls:
            continue
        busy = union((e["ts"], e["ts"] + e["dur"]) for e in evs if e.get("cat") in ("cpu_op", "user_annotation"))
        threads[tid] = (len(calls), sum(e["dur"] for e in calls), busy)
        call_ts = sorted(e["ts"] for e in calls)
        for label, pattern in ops:
            matched = sorted((e for e in evs if e.get("cat") == "cpu_op" and pattern.search(e["name"])),
                             key=lambda e: (e["ts"], -e["dur"]))
            outer_end = float("-inf")
            for e in matched:
                if e["ts"] < outer_end:
                    continue
                outer_end = e["ts"] + e["dur"]
                inside = sum(1 for t in call_ts if e["ts"] <= t < outer_end)
                g = groups[label]
                g[0] += 1
                g[1] += e["dur"]
                g[2] += inside
    return threads, groups


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", action="append", required=True, help="LABEL=GLOB of torch.profiler traces")
    parser.add_argument("--step-boundary", required=True)
    parser.add_argument("--cluster-gap-ms", type=float, default=20.0)
    parser.add_argument("--steps", default="-2:")
    parser.add_argument("--op", action="append", default=[], help="LABEL:REGEX on cpu_op names")
    parser.add_argument("--ranks", default=None)
    args = parser.parse_args()

    boundary = re.compile(args.step_boundary)
    ops = [(o.split(":", 1)[0], re.compile(o.split(":", 1)[1])) for o in args.op]
    lo_s, hi_s = (args.steps.split(":") + [""])[:2]
    step_slice = slice(int(lo_s) if lo_s else None, int(hi_s) if hi_s else None)
    wanted = {int(r) for r in args.ranks.split(",")} if args.ranks else None

    results = []
    for spec in args.trace:
        label, pattern = spec.split("=", 1)
        files = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"(\d+)\D*$", p).group(1)))
        if not files:
            parser.error(f"--trace {spec}: no files match")
        thread_rows, group_rows, n = defaultdict(lambda: [0.0, 0.0, 0.0]), defaultdict(lambda: [0.0, 0.0, 0.0]), 0
        win = 0.0
        for i, path in enumerate(files):
            if wanted is not None and i not in wanted:
                continue
            events = load(path)
            found = windows(events, boundary, args.cluster_gap_ms * 1e3)
            chosen = found[step_slice]
            if not chosen:
                print(f"{label} rank {i}: --steps {args.steps} selects none of its {len(found)} step windows, skipped")
                continue
            for lo, hi in chosen:
                threads, groups = analyze(events, lo, hi, ops)
                ranked = sorted(threads.items(), key=lambda kv: -kv[1][0])
                for rank_in_thread, (_, values) in enumerate(ranked):
                    key = "main thread (most launches)" if rank_in_thread == 0 else f"thread #{rank_in_thread + 1} by launches"
                    for j in range(3):
                        thread_rows[key][j] += values[j] / len(chosen)
                for g, values in groups.items():
                    for j in range(3):
                        group_rows[g][j] += values[j] / len(chosen)
                win += (hi - lo) / len(chosen)
            n += 1
        if not n:
            parser.error(f"{label}: no step windows selected; check --step-boundary, --cluster-gap-ms and --steps")
        results.append((label, {k: [v / n for v in vals] for k, vals in thread_rows.items()},
                        {k: [v / n for v in vals] for k, vals in group_rows.items()}, win / n))

    two = len(results) == 2
    labels = [r[0] for r in results]
    print(f"host step window ms: " + ", ".join(f"{label} {r[3] / 1e3:.1f}" for label, r in zip(labels, results)))
    print()
    print("| thread | metric | " + " | ".join(labels) + (" | delta |" if two else " |"))
    print("|---|---|" + "---:|" * (len(results) + (1 if two else 0)))
    keys = sorted({k for r in results for k in r[1]})
    for k in keys:
        for j, metric in enumerate(("launch calls / step", "ms in launch calls", "busy ms")):
            vals = [r[1].get(k, [0, 0, 0])[j] / (1e3 if j else 1) for r in results]
            print(f"| {k} | {metric} | " + " | ".join(f"{v:.1f}" for v in vals) + (f" | {vals[1] - vals[0]:+.1f} |" if two else " |"))
    if ops:
        print()
        print("| op group | metric | " + " | ".join(labels) + (" | delta |" if two else " |"))
        print("|---|---|" + "---:|" * (len(results) + (1 if two else 0)))
        for label, _ in ops:
            for j, metric in enumerate(("calls / step", "inclusive host ms", "launch calls inside")):
                vals = [r[2].get(label, [0, 0, 0])[j] / (1e3 if j == 1 else 1) for r in results]
                print(f"| {label} | {metric} | " + " | ".join(f"{v:.1f}" for v in vals)
                      + (f" | {vals[1] - vals[0]:+.1f} |" if two else " |"))


if __name__ == "__main__":
    main()
