# /// script
# requires-python = ">=3.10"
# ///
"""Split each NCCL collective's time into waiting for the last rank to arrive and the transfer itself, across ranks.

An NCCL kernel's duration on one rank includes waiting for its peers, so a slow collective is either slow to
transfer or waiting for a late rank. Given one torch.profiler trace per rank from one node (timestamps share a
clock), this matches the Nth NCCL kernel of each (launching op without dims, kernel name, GPU stream) across ranks
(the stream separates collectives of different process groups that share an op name; `--no-stream-key` drops it). For each
matched call: `arrival skew` = last rank's start minus first rank's start; `transfer` = earliest end minus last
start (the time all ranks were present, a lower bound on the real transfer); each rank's `wait` = last start minus
its own start. Calls are reported if their first rank's start falls in the window, which is the window
`top_kernels.py` uses on the first trace (`--annotation`, `--annotation-index`, `--annotation-span`, default the last
`forward`). Rows group calls by launching op (dims dropped, since token counts differ across ranks): calls, summed
wait over ranks, summed transfer, and which rank arrived last how often. `--per-rank` adds each rank's total wait
and how often it was last. All ranks must run the same collective sequence; the script stops if the per-key call
counts differ. `--comm REGEX` replaces the NCCL kernel set with the kernels whose name matches REGEX, for other
collectives that wait for their peers inside the kernel, e.g. `'nccl|deep_ep::intranode'` for DeepEP's dispatch and
combine kernels next to NCCL.

Traces are loaded one at a time and reduced to their NCCL kernels, so memory stays near one trace's size.

Usage:
  uv run --script collective_skew.py "traces/T6/trace_*.json.gz" --annotation-index -2 --annotation-span 2 \\
    [--per-rank] [--per-call 20] [--top 30] [--comm 'nccl|deep_ep::intranode'] [--csv out.csv]
"""

import argparse
import csv
import glob
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from top_kernels import GPU_CATS, call_sites, is_comm
from trace_events import is_marker, pick, read_trace


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("traces", help="glob of per-rank traces; rank = trailing integer in the file name")
    p.add_argument("--annotation", default="forward")
    p.add_argument("--annotation-index", type=int, default=-1)
    p.add_argument("--annotation-span", type=int, default=1)
    p.add_argument("--per-rank", action="store_true")
    p.add_argument("--no-stream-key", action="store_true",
                   help="match calls without the GPU stream id (for traces whose stream ids differ across ranks)")
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--per-call", type=int, default=0, metavar="N",
                   help="also list the N calls with the most summed wait, with the first rank's full launching op")
    p.add_argument("--comm", default=None, metavar="REGEX",
                   help="regex of the collective kernels to match (default: NCCL kernels)")
    p.add_argument("--csv")
    return p.parse_args()


def rank_of(path):
    return int(re.findall(r"(\d+)", Path(path).name)[-1])


def drop_dims(site):
    return re.sub(r"\s*\[[\[\]\d,\s]*\]", "", site).strip()


def load_rank(path, args):
    xs = [e for e in read_trace(path)["traceEvents"] if e.get("ph") == "X"]
    is_collective = re.compile(args.comm).search if args.comm else is_comm
    collectives = sorted((e for e in xs if e.get("cat") in GPU_CATS and is_collective(e["name"])), key=lambda e: e["ts"])
    sites = call_sites(xs, collectives)
    steps = sorted(e["ts"] for e in xs if e.get("cat") == "user_annotation" and is_marker(e["name"], args.annotation))
    window = None
    if steps:
        start = pick(steps, args.annotation_index, f"CPU-side user_annotation `{args.annotation}`")
        later = [t for t in steps if t > start]
        window = (start, later[args.annotation_span - 1] if len(later) >= args.annotation_span else float("inf"))
    calls = defaultdict(list)
    for e in collectives:
        site = drop_dims(sites.get(e["args"].get("correlation"), "<no enclosing cpu_op>"))
        key = (site, e["name"]) if args.no_stream_key else (site, e["name"], e["tid"])
        calls[key].append((e["ts"], e["ts"] + e["dur"], sites.get(e["args"].get("correlation"), "")))
    return calls, window


def main():
    args = parse_args()
    paths = sorted(glob.glob(args.traces), key=rank_of)
    if len(paths) < 2:
        sys.exit(f"need at least two per-rank traces, matched {len(paths)}")
    per_rank, windows = {}, {}
    for path in paths:
        per_rank[rank_of(path)], windows[rank_of(path)] = load_rank(path, args)
    ranks = sorted(per_rank)
    window = windows[ranks[0]]
    keys = set().union(*(per_rank[r].keys() for r in ranks))
    rows, rank_wait, rank_last, call_rows = [], Counter(), Counter(), []
    for key in keys:
        counts = {r: len(per_rank[r].get(key, [])) for r in ranks}
        if len(set(counts.values())) != 1:
            sys.exit(f"call counts differ across ranks for {key}: {counts}")
        wait = transfer = skew = 0.0
        n, last = 0, Counter()
        for i in range(counts[ranks[0]]):
            starts = {r: per_rank[r][key][i][0] for r in ranks}
            ends = {r: per_rank[r][key][i][1] for r in ranks}
            first = min(starts.values())
            if window and not (window[0] <= first < window[1]):
                continue
            latest = max(starts.values())
            late_rank = max(starts, key=starts.get)
            n += 1
            last[late_rank] += 1
            rank_last[late_rank] += 1
            call_wait = sum(latest - starts[r] for r in ranks)
            call_transfer = max(0.0, min(ends.values()) - latest)
            skew += latest - first
            transfer += call_transfer
            wait += call_wait
            for r in ranks:
                rank_wait[r] += latest - starts[r]
            call_rows.append((call_wait / 1e3, call_transfer / 1e3, (first - window[0]) / 1e3 if window else first / 1e3,
                              late_rank, per_rank[ranks[0]][key][i][2]))
        if n:
            rows.append((key, n, wait / 1e3, transfer / 1e3, skew / 1e3, last))
    rows.sort(key=lambda row: -row[2])
    print(f"# Collective arrival skew over {len(ranks)} ranks: `{args.traces}`\n")
    print(f"- window on rank {ranks[0]}: `{args.annotation}` [{args.annotation_index}] span {args.annotation_span}")
    total_wait, total_transfer = sum(r[2] for r in rows), sum(r[3] for r in rows)
    print(f"- matched calls in window: {sum(r[1] for r in rows)}; wait summed over ranks: {total_wait:.1f} ms "
          f"(mean per rank {total_wait / len(ranks):.1f} ms); transfer, once per call: {total_transfer:.1f} ms. "
          "Compare the per-rank mean wait with transfer, not the sum over ranks.\n")
    print("| # | calls | wait ms (sum over ranks) | transfer ms | mean arrival skew ms | last to arrive (rank:count) | launching op | kernel |")
    print("|---|---|---|---|---|---|---|---|")
    for i, (key, n, wait, transfer, skew, last) in enumerate(rows[: args.top], 1):
        lasts = " ".join(f"{r}:{c}" for r, c in last.most_common(4))
        print(f"| {i} | {n} | {wait:.1f} | {transfer:.1f} | {skew / n:.2f} | {lasts} | {key[0]} | {key[1][:40]} |")
    if args.per_rank:
        print("\n| rank | total wait ms | times last to arrive |")
        print("|---|---|---|")
        for r in ranks:
            print(f"| {r} | {rank_wait[r] / 1e3:.1f} | {rank_last[r]} |")
    if args.per_call:
        print(f"\n| wait ms (sum) | transfer ms | starts at ms (window) | last rank | launching op (rank {ranks[0]}) |")
        print("|---|---|---|---|---|")
        for wait, transfer, at, late_rank, site in sorted(call_rows, key=lambda c: -c[0])[: args.per_call]:
            print(f"| {wait:.1f} | {transfer:.2f} | {at:.1f} | {late_rank} | {site[:90]} |")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["launching_op", "kernel", "calls", "wait_ms_sum", "transfer_ms", "mean_skew_ms", "last_counts"])
            for key, n, wait, transfer, skew, last in rows:
                w.writerow([key[0], key[1], n, f"{wait:.3f}", f"{transfer:.3f}", f"{skew / n:.3f}",
                            " ".join(f"{r}:{c}" for r, c in last.most_common())])


if __name__ == "__main__":
    main()
