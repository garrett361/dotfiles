# /// script
# requires-python = ">=3.10"
# ///
"""Per-phase host time across ranks, from host_phases/sitecustomize.py output (`phases_rank<R>.jsonl`, one per rank).

Prints, for every timed function (HOST_PHASES): calls per rank, and seconds per rank (summed over its calls) as min,
median and max over ranks, with the slowest rank; then its span on the merged wall clock (first start and last end
over ranks, relative to the earliest event of any rank), which shows phases that wait on the last rank. For every
summed function (HOST_PHASES_AGG): seconds and bytes per rank (median and max) and the median rank's rate in GB/s.
`--rank-table NAME` prints every rank's seconds for one function (substring match), to find slow nodes. Ranks are
labelled with the host each file records; `--hosts FILE` (lines `RANK HOST`) overrides those labels.
`--window START END` keeps events starting between those seconds of the merged clock.

Usage: uv run --script host_phases.py DIR [--window 0 300] [--rank-table read_data] [--csv out.csv]
"""

import argparse
import csv
import glob
import json
import os
import re
import statistics
from collections import defaultdict


def load(directory):
    ranks = {}
    for path in glob.glob(os.path.join(directory, "phases_rank*.jsonl")):
        rank = int(re.search(r"phases_rank(\d+)\.jsonl", path).group(1))
        events, agg, host = [], {}, None
        with open(path) as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "agg" in record:
                    agg = record["agg"]
                elif "host" in record:
                    host = record["host"]
                else:
                    events.append(record)
        ranks[rank] = (events, agg, host)
    return ranks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory")
    parser.add_argument("--window", nargs=2, type=float)
    parser.add_argument("--rank-table")
    parser.add_argument("--hosts")
    parser.add_argument("--csv")
    args = parser.parse_args()

    ranks = load(args.directory)
    if not ranks:
        raise SystemExit(f"no phases_rank*.jsonl in {args.directory}")
    origin = min((e["t0"] for events, _, _ in ranks.values() for e in events), default=0.0)
    hosts = {rank: host for rank, (_, _, host) in ranks.items() if host}
    if args.hosts:
        with open(args.hosts) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    hosts[int(parts[0])] = parts[1]

    seconds = defaultdict(dict)
    calls = defaultdict(dict)
    first = defaultdict(lambda: float("inf"))
    last = defaultdict(float)
    for rank, (events, _, _) in ranks.items():
        for event in events:
            start, end = event["t0"] - origin, event["t1"] - origin
            if args.window and not args.window[0] <= start <= args.window[1]:
                continue
            name = event["n"]
            seconds[name][rank] = seconds[name].get(rank, 0.0) + end - start
            calls[name][rank] = calls[name].get(rank, 0) + 1
            first[name] = min(first[name], start)
            last[name] = max(last[name], end)

    rows = []
    print(f"{len(ranks)} ranks; times in seconds; span on the merged clock from the first event")
    print(f"{'function':64} {'calls':>6} {'min':>8} {'median':>8} {'max':>8} {'slowest':>14} {'start':>8} {'end':>8}")
    for name in sorted(seconds, key=lambda n: first[n]):
        per_rank = seconds[name]
        values = list(per_rank.values())
        slowest = max(per_rank, key=per_rank.get)
        label = f"{hosts[slowest]} r{slowest}" if slowest in hosts else f"rank {slowest}"
        median_calls = statistics.median(calls[name].values())
        row = [name, median_calls, min(values), statistics.median(values), max(values), label, first[name], last[name]]
        rows.append(row)
        print(
            f"{name[-64:]:64} {median_calls:6g} {row[2]:8.2f} {row[3]:8.2f} {row[4]:8.2f} {label[-14:]:>14} "
            f"{first[name]:8.1f} {last[name]:8.1f}"
        )

    agg_seconds = defaultdict(dict)
    agg_bytes = defaultdict(dict)
    for rank, (_, agg, _) in ranks.items():
        for name, threads in agg.items():
            agg_seconds[name][rank] = sum(entry[1] for entry in threads.values())
            agg_bytes[name][rank] = sum(entry[2] for entry in threads.values())
    if agg_seconds:
        print(f"\n{'summed function':64} {'s median':>9} {'s max':>8} {'GB median':>10} {'GB/s':>7}")
        for name in sorted(agg_seconds):
            secs = statistics.median(agg_seconds[name].values())
            gb = statistics.median(agg_bytes[name].values()) / 1e9
            rate = gb / secs if secs > 0 and gb > 0 else float("nan")
            print(f"{name[-64:]:64} {secs:9.2f} {max(agg_seconds[name].values()):8.2f} {gb:10.2f} {rate:7.2f}")

    if args.rank_table:
        matches = [n for n in seconds if args.rank_table in n]
        for name in matches:
            print(f"\n{name}: seconds per rank")
            for rank in sorted(seconds[name], key=seconds[name].get, reverse=True):
                print(f"  {hosts.get(rank, '')} rank {rank}: {seconds[name][rank]:.2f}")
            by_host = defaultdict(list)
            for rank, value in seconds[name].items():
                by_host[hosts.get(rank, "?")].append(value)
            print(f"{name}: max seconds per host")
            for host, values in sorted(by_host.items(), key=lambda item: max(item[1]), reverse=True):
                print(f"  {host}: max {max(values):.2f}, median {statistics.median(values):.2f} over {len(values)} ranks")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["function", "calls", "min_s", "median_s", "max_s", "slowest", "start_s", "end_s"])
            writer.writerows(rows)


if __name__ == "__main__":
    main()
