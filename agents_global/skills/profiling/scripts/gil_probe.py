# /// script
# requires-python = ">=3.10"
# ///
"""GIL wait windows and garbage collections per rank, from gil_probe/sitecustomize.py output (`gil_rank<R>.jsonl`).

Per rank: the flagged windows (each a probe window whose longest wake-up delay exceeded the capture's GIL_PROBE_MS),
their worst delay in ms and the summed delay in seconds (`late_s`, a lower bound on how long a thread that wanted the
GIL waited), then the collections per generation with their count, summed and longest pause. Ranks are sorted by
summed delay, so the rank whose threads fought hardest for the GIL comes first. `--window START END` keeps records
starting between those seconds after the earliest record of any rank (`--origin UNIX` sets that zero instead, e.g. a
log line's time). `--timeline RANK` prints that rank's flagged windows and the collections longer than `--gc-ms`
(default 10) in time order, to line them up with log lines or step times. Times print relative to the zero.

Usage: uv run --script gil_probe.py DIR [--window 0 600] [--origin UNIX] [--timeline 0] [--gc-ms 10] [--top 16]
"""

import argparse
import glob
import json
import os
import re
from collections import defaultdict


def load(directory):
    ranks = {}
    for path in glob.glob(os.path.join(directory, "gil_rank*.jsonl")):
        rank = int(re.search(r"gil_rank(\d+)\.jsonl", path).group(1))
        records = []
        with open(path) as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        ranks[rank] = records
    return ranks


def start(record):
    return record["gil"][0] if "gil" in record else record["t0"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory")
    parser.add_argument("--window", nargs=2, type=float)
    parser.add_argument("--origin", type=float)
    parser.add_argument("--timeline", type=int)
    parser.add_argument("--gc-ms", type=float, default=10.0)
    parser.add_argument("--top", type=int, default=16)
    args = parser.parse_args()

    ranks = load(args.directory)
    if not ranks:
        raise SystemExit(f"no gil_rank*.jsonl in {args.directory}")
    origin = args.origin if args.origin is not None else min(start(r) for rs in ranks.values() for r in rs)
    for rank, records in ranks.items():
        ranks[rank] = [r for r in records if not args.window or args.window[0] <= start(r) - origin <= args.window[1]]

    rows = []
    for rank, records in ranks.items():
        windows = [r for r in records if "gil" in r]
        collections = defaultdict(list)
        for r in records:
            if "gc" in r:
                collections[r["gc"]].append(r["t1"] - r["t0"])
        rows.append(
            (
                sum(w["late_s"] for w in windows),
                rank,
                len(windows),
                max((w["max_ms"] for w in windows), default=0.0),
                collections,
            )
        )
    rows.sort(reverse=True)
    print(f"{len(ranks)} ranks; times relative to {origin:.3f}")
    print(f"{'rank':>5} {'windows':>8} {'worst ms':>9} {'late s':>8}   collections per generation: count, sum s, max s")
    for late_s, rank, count, worst, collections in rows[: args.top]:
        gcs = "  ".join(f"gen{g}: {len(p)}, {sum(p):.3f}, {max(p):.3f}" for g, p in sorted(collections.items()))
        print(f"{rank:5d} {count:8d} {worst:9.1f} {late_s:8.3f}   {gcs}")

    if args.timeline is not None:
        print(f"\nrank {args.timeline} timeline (s from zero)")
        for r in sorted(ranks.get(args.timeline, []), key=start):
            if "gil" in r:
                t0, t1 = r["gil"]
                print(
                    f"{t0 - origin:10.3f} {t1 - origin:10.3f}  GIL wait: worst {r['max_ms']:.1f} ms, {r['late_s']:.3f} s late, {r['late']} late wake-ups"
                )
            elif (r["t1"] - r["t0"]) * 1e3 >= args.gc_ms:
                print(
                    f"{r['t0'] - origin:10.3f} {r['t1'] - origin:10.3f}  gc gen{r['gc']} {r['t1'] - r['t0']:.3f} s on {r['th']}, {r['collected']} collected"
                )


if __name__ == "__main__":
    main()
