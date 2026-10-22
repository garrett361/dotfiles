# /// script
# requires-python = ">=3.10"
# ///
"""Account for a training step's wall time, per arm, as rows that sum exactly to the step window.

Each step window (from the end of one cluster of `--step-boundary` kernels, e.g. the optimizer's, to the end of
the next) is swept on one GPU. Every instant goes to exactly one row:
- compute: some non-communication kernel, memcpy or memset runs on any stream. The instant is split evenly
  across the kernels running then, and each kernel's share goes to its `--category` (first match wins, raw
  names, unmatched kernels go to "other compute").
- exposed comm: only communication kernels (`--comm`, default NCCL) run, labeled by collective
  (AllGather, ReduceScatter, AllReduce, SendRecv/AllToAll, Broadcast, ...).
- idle: nothing runs. Each idle gap is classified by the kernel that ends it. If that kernel's launch call
  ended after the gap began, the host was late ("idle, host late: ..."), labeled with what the launching
  thread was inside at the gap start (torch traces: blocking CUDA call if any, else innermost cpu_op within
  the innermost user_annotation; nsys: the CUDA API call if any, else "host code"). Otherwise the kernel was
  already queued and waited on a device-side dependency ("idle, queued (stream wait)").

`--step-boundary` must match kernels that run only at the end of each step, normally the optimizer's:
`FusedAdamMathFunctor` for torch.optim Adam/AdamW with `fused=True` (`FusedSgdMathFunctor` for SGD),
`multi_tensor_apply_kernel` for `foreach=True` optimizers. The latter also matches every other `_foreach_*`
kernel (e.g. grad clipping's `_foreach_norm`), so it only works when none run mid-step: on a prime-rl trace it
cut 4 real steps into 70 windows. Check with `--per-rank`, which prints each rank's window count and mean
window; both should match the traced steps. Boundary kernels less than `--cluster-gap-ms` (default 20) apart merge
into one cluster, so for steps shorter than that, lower it.

Inputs, repeatable, one per arm: `--trace LABEL=GLOB` (torch.profiler chrome traces, one file per rank) or
`--nsys LABEL=SQLITE` (one export with every rank; ranks are deviceIds). `--steps LO:HI` picks step windows by
index (Python slice over each rank's windows; default the last two complete steps; write negative bounds as
`--steps=-3:`) and rows are averaged per step, then over the ranks that have a selected window. With two arms a
delta column is added. `--untraced LABEL=SECONDS` adds the untraced median step time per arm, and the table then
ends with a "tracing overhead / residual" row so the delta column sums to the untraced step delta. `--per-rank`
prints each rank's window and partition, to check that one rank is representative. `--host-depth N` keeps N
levels of cpu_op names in host-late labels. Collectives that launch no GPU kernel (gloo) show up as host-late
idle, and a `--comm` regex that matches nothing moves the NCCL kernels into compute rows.

The header also reports the number of GPU activities (kernels, memcpys, memsets) per step.

Usage:
  uv run --script step_accounting.py --trace "bf16=traces/bf16/trace_*.json.gz" \\
    --trace "fp8=traces/fp8/trace_*.json.gz" --step-boundary "FusedAdamMathFunctor" \\
    --category "FP8 GEMM:sm90_fp8_gemm|fp8_gemm" --category "BF16 GEMM:nvjet|cutlass" \\
    --untraced bf16=0.652 --untraced fp8=0.696 [--per-rank] [--top-idle 12] [--csv out.csv]
  uv run --script step_accounting.py --nsys "bf16=nsys/bf16.sqlite" --nsys "fp8=nsys/fp8.sqlite" \\
    --step-boundary "FusedAdamMathFunctor" --steps 4:11 ...
"""

import argparse
import bisect
import csv
import glob
import gzip
import heapq
import json
import re
import sqlite3
from collections import defaultdict

BLOCKING = re.compile(
    r"cudaStreamSynchronize|cudaDeviceSynchronize|cudaEventSynchronize|cudaMemcpy(?!Async)|cuStreamSynchronize|"
    r"cuCtxSynchronize|cuEventSynchronize|cuMemcpyDtoH(?!Async)"
)
COLLECTIVES = (
    ("AllGather", r"AllGather"),
    ("ReduceScatter", r"ReduceScatter"),
    ("AllReduce", r"AllReduce"),
    ("SendRecv/AllToAll", r"SendRecv|AllToAll|Send|Recv"),
    ("Broadcast", r"Broadcast"),
)


class Rank:
    """GPU activity and host context for one rank: `gpu` rows are (start, end, name, launch_end, launch_thread)."""

    def __init__(self, gpu, host_at):
        self.gpu = sorted(gpu)
        self.host_at = host_at


def load_torch(path, host_depth):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        events = [e for e in json.load(f)["traceEvents"] if e.get("ph") == "X"]
    launches = {}
    host = defaultdict(list)
    for e in events:
        cat = e.get("cat")
        if cat in ("cuda_runtime", "cuda_driver"):
            if "correlation" in e.get("args", {}):
                launches[e["args"]["correlation"]] = e
            host[(e["pid"], e["tid"])].append(e)
        elif cat in ("cpu_op", "user_annotation"):
            host[(e["pid"], e["tid"])].append(e)
    gpu = []
    for e in events:
        if e.get("cat") not in ("kernel", "gpu_memcpy", "gpu_memset"):
            continue
        launch = launches.get(e.get("args", {}).get("correlation"))
        launch_end = launch["ts"] + launch.get("dur", 0) if launch else None
        thread = (launch["pid"], launch["tid"]) if launch else None
        gpu.append((e["ts"], e["ts"] + e["dur"], e["name"], launch_end, thread))
    starts = {}
    for key, evs in host.items():
        evs.sort(key=lambda e: (e["ts"], -e.get("dur", 0)))
        starts[key] = [e["ts"] for e in evs]

    def host_at(thread, t):
        evs = host.get(thread, [])
        upper = bisect.bisect_right(starts.get(thread, []), t)
        ops, annotation, blocking = [], None, None
        for e in reversed(evs[max(0, upper - 4000):upper]):
            if e["ts"] + e.get("dur", 0) < t:
                continue
            cat = e.get("cat")
            if cat in ("cuda_runtime", "cuda_driver"):
                if blocking is None and BLOCKING.search(e["name"]):
                    blocking = e["name"]
            elif cat == "user_annotation":
                if annotation is None:
                    annotation = e["name"]
            elif len(ops) < host_depth:
                ops.append(e["name"])
        where = " > ".join(reversed(ops)) if ops else "no cpu_op"
        label = f"{where} in {annotation}" if annotation else where
        if blocking:
            return f"blocked in {blocking}: {label}"
        return label

    return Rank(gpu, host_at)


def load_nsys(path):
    db = sqlite3.connect(path)
    names = dict(db.execute("select id, value from StringIds"))
    api = defaultdict(list)
    launch_by_corr = {}
    for start, end, corr, tid, name_id in db.execute(
        "select start, end, correlationId, globalTid, nameId from CUPTI_ACTIVITY_KIND_RUNTIME"
    ):
        name = names.get(name_id, "")
        api[tid].append((start / 1e3, end / 1e3, name))
        launch_by_corr[(tid >> 24, corr)] = (end / 1e3, tid)
    for tid in api:
        api[tid].sort()
    api_starts = {tid: [a[0] for a in rows] for tid, rows in api.items()}
    per_device = defaultdict(list)
    queries = [
        ("CUPTI_ACTIVITY_KIND_KERNEL", "select k.start, k.end, k.deviceId, k.globalPid, k.correlationId, k.demangledName from CUPTI_ACTIVITY_KIND_KERNEL k"),
        ("CUPTI_ACTIVITY_KIND_MEMCPY", "select start, end, deviceId, globalPid, correlationId, null from CUPTI_ACTIVITY_KIND_MEMCPY"),
        ("CUPTI_ACTIVITY_KIND_MEMSET", "select start, end, deviceId, globalPid, correlationId, null from CUPTI_ACTIVITY_KIND_MEMSET"),
    ]
    tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
    for table, query in queries:
        if table not in tables:
            continue
        for start, end, device, pid, corr, name_id in db.execute(query):
            name = names.get(name_id, "") if name_id is not None else table.rsplit("_", 1)[-1].lower()
            launch_end, tid = launch_by_corr.get((pid >> 24, corr), (None, None))
            per_device[device].append((start / 1e3, end / 1e3, name, launch_end, tid))

    def host_at(tid, t):
        rows = api.get(tid, [])
        upper = bisect.bisect_right(api_starts.get(tid, []), t)
        for start, end, name in reversed(rows[max(0, upper - 50):upper]):
            if end >= t:
                return f"blocked in {name}" if BLOCKING.search(name) else f"in {name}"
        return "host code (no CUDA call)"

    return {device: Rank(rows, host_at) for device, rows in sorted(per_device.items())}


def step_windows(rank, boundary, gap_us):
    marks = sorted((s, e) for s, e, name, _, _ in rank.gpu if boundary.search(name))
    ends = [e for (_, e), (ns, _) in zip(marks, marks[1:] + [(float("inf"), 0)]) if ns - e > gap_us]
    return list(zip(ends[:-1], ends[1:]))


def collective(name):
    for label, pattern in COLLECTIVES:
        if re.search(pattern, name):
            return label
    return "other comm"


def account(rank, lo, hi, categories, comm, args):
    rows = defaultdict(float)
    acts = [g for g in rank.gpu if g[1] > lo and g[0] < hi]
    labels = []
    for s, e, name, _, _ in acts:
        if comm.search(name):
            labels.append(("comm", "exposed comm: " + collective(name)))
        else:
            label = next((lab for lab, pat in categories if pat.search(name)), "other compute")
            labels.append(("compute", "compute: " + label))
    points = sorted({lo, hi} | {max(lo, min(hi, x)) for g in acts for x in (g[0], g[1])})
    by_start = sorted(range(len(acts)), key=lambda i: acts[i][0])
    active = set()
    pointer = 0
    ends = []
    idle_gaps = []
    for t0, t1 in zip(points, points[1:]):
        while pointer < len(by_start) and acts[by_start[pointer]][0] <= t0:
            active.add(by_start[pointer])
            heapq.heappush(ends, (acts[by_start[pointer]][1], by_start[pointer]))
            pointer += 1
        while ends and ends[0][0] <= t0:
            active.discard(heapq.heappop(ends)[1])
        dt = t1 - t0
        if dt <= 0:
            continue
        compute = [i for i in active if labels[i][0] == "compute"]
        comms = [i for i in active if labels[i][0] == "comm"]
        chosen = compute or comms
        if chosen:
            for i in chosen:
                rows[labels[i][1]] += dt / len(chosen)
        elif idle_gaps and abs(idle_gaps[-1][1] - t0) < 1e-6:
            idle_gaps[-1][1] = t1
        else:
            idle_gaps.append([t0, t1])
    starts_sorted = sorted(rank.gpu, key=lambda g: g[0])
    start_keys = [g[0] for g in starts_sorted]
    for g0, g1 in idle_gaps:
        idx = bisect.bisect_left(start_keys, g1 - 1e-6)
        nxt = starts_sorted[idx] if idx < len(starts_sorted) else None
        if nxt is None or nxt[3] is None:
            label = "idle, unknown"
        elif nxt[3] > g0:
            label = "idle, host late: " + rank.host_at(nxt[4], g0)
        else:
            label = "idle, queued (stream wait)"
        rows[label] += g1 - g0
    launches = sum(1 for g in acts if lo <= g[0] < hi)
    return rows, launches


def fold_idle(rows, top):
    host = sorted(((k, v) for k, v in rows.items() if k.startswith("idle, host late")), key=lambda kv: -kv[1])
    out = {k: v for k, v in rows.items() if not k.startswith("idle, host late")}
    for k, v in host[:top]:
        out[k] = v
    rest = sum(v for _, v in host[top:])
    if rest:
        out["idle, host late: other sites"] = rest
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", action="append", default=[], help="LABEL=GLOB of torch.profiler traces")
    parser.add_argument("--nsys", action="append", default=[], help="LABEL=SQLITE nsys export")
    parser.add_argument("--step-boundary", required=True, help="regex of the kernels whose cluster ends a step")
    parser.add_argument("--cluster-gap-ms", type=float, default=20.0)
    parser.add_argument("--steps", default="-2:", help="slice of step windows to average (default last two)")
    parser.add_argument("--category", action="append", default=[], help="LABEL:REGEX for compute kernels")
    parser.add_argument("--comm", default=r"nccl|NCCL", help="regex of communication kernels")
    parser.add_argument("--untraced", action="append", default=[], help="LABEL=SECONDS untraced median step")
    parser.add_argument("--ranks", default=None, help="comma list of ranks (file order or deviceId) to include")
    parser.add_argument("--host-depth", type=int, default=1)
    parser.add_argument("--top-idle", type=int, default=10, help="host-late idle sites kept per arm, rest folded")
    parser.add_argument("--per-rank", action="store_true")
    parser.add_argument("--csv", default=None)
    args = parser.parse_args()

    categories = [(c.split(":", 1)[0], re.compile(c.split(":", 1)[1])) for c in args.category]
    comm = re.compile(args.comm)
    boundary = re.compile(args.step_boundary)
    lo_s, hi_s = (args.steps.split(":") + [""])[:2]
    step_slice = slice(int(lo_s) if lo_s else None, int(hi_s) if hi_s else None)
    wanted = {int(r) for r in args.ranks.split(",")} if args.ranks else None

    arms = []
    for spec in args.trace:
        label, pattern = spec.split("=", 1)
        files = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"(\d+)\D*$", p).group(1)))
        if not files:
            parser.error(f"--trace {spec}: no files match")
        ranks = {i: load_torch(p, args.host_depth) for i, p in enumerate(files) if wanted is None or i in wanted}
        arms.append((label, ranks))
    for spec in args.nsys:
        label, path = spec.split("=", 1)
        ranks = {d: r for d, r in load_nsys(path).items() if wanted is None or d in wanted}
        arms.append((label, ranks))
    untraced = {s.split("=")[0]: float(s.split("=")[1]) * 1e3 for s in args.untraced}

    results = []
    for label, ranks in arms:
        total = defaultdict(float)
        windows, launch_counts, n = [], [], 0
        for rank_id, rank in ranks.items():
            found = step_windows(rank, boundary, args.cluster_gap_ms * 1e3)
            chosen = found[step_slice]
            if not chosen:
                print(f"{label} rank {rank_id}: --steps {args.steps} selects none of its {len(found)} step windows, "
                      "skipped")
                continue
            per_rank = defaultdict(float)
            for lo, hi in chosen:
                rows, launches = account(rank, lo, hi, categories, comm, args)
                for k, v in rows.items():
                    per_rank[k] += v / len(chosen)
                launch_counts.append(launches)
            windows.append(sum(hi - lo for lo, hi in chosen) / len(chosen))
            if args.per_rank:
                comp = sum(v for k, v in per_rank.items() if k.startswith("compute"))
                com = sum(v for k, v in per_rank.items() if k.startswith("exposed comm"))
                idle = sum(v for k, v in per_rank.items() if k.startswith("idle"))
                print(f"{label} rank {rank_id}: {len(chosen)} of {len(found)} steps, "
                      f"window {(comp + com + idle) / 1e3:.1f} ms = compute {comp / 1e3:.1f} + "
                      f"exposed comm {com / 1e3:.1f} + idle {idle / 1e3:.1f}")
            for k, v in per_rank.items():
                total[k] += v
            n += 1
        if not n:
            parser.error(f"{label}: no step windows selected; check --step-boundary, --cluster-gap-ms and --steps")
        mean = {k: v / n / 1e3 for k, v in total.items()}
        results.append((label, fold_idle(mean, args.top_idle), sum(windows) / len(windows) / 1e3,
                        sum(launch_counts) / len(launch_counts)))
        print(f"{label}: {n} ranks, mean window {results[-1][2]:.1f} ms, {results[-1][3]:.0f} GPU activities per step")

    keys = sorted({k for _, rows, _, _ in results for k in rows}, key=lambda k: (k.split(":")[0], k))
    header = "| row | " + " | ".join(f"{label} ms" for label, _, _, _ in results)
    two = len(results) == 2
    print()
    print(header + (f" | delta ms ({results[1][0]} - {results[0][0]}) |" if two else " |"))
    print("|---|" + "---:|" * (len(results) + (1 if two else 0)))
    table = []
    for k in keys:
        vals = [rows.get(k, 0.0) for _, rows, _, _ in results]
        table.append([k] + vals + ([vals[1] - vals[0]] if two else []))
    if two:
        table.sort(key=lambda r: (r[0].split(":")[0], -abs(r[-1])))
    for row in table:
        print(f"| {row[0][:150]} | " + " | ".join(f"{v:.2f}" for v in row[1:]) + " |")
    windows = [w for _, _, w, _ in results]
    print("| **traced step window** | " + " | ".join(f"**{w:.2f}**" for w in windows)
          + (f" | **{windows[1] - windows[0]:.2f}** |" if two else " |"))
    if untraced and all(label in untraced for label, _, _, _ in results):
        un = [untraced[label] for label, _, _, _ in results]
        over = [u - w for u, w in zip(un, windows)]
        print("| tracing overhead / residual (untraced minus traced window) | " + " | ".join(f"{v:.2f}" for v in over)
              + (f" | {over[1] - over[0]:.2f} |" if two else " |"))
        print("| **untraced median step** | " + " | ".join(f"**{v:.2f}**" for v in un)
              + (f" | **{un[1] - un[0]:.2f}** |" if two else " |"))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["row"] + [label for label, _, _, _ in results] + (["delta"] if two else []))
            writer.writerows(table)
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
