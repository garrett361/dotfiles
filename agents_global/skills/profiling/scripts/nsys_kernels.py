"""Per-kernel GPU time from an nsys SQLite export, optionally for one device and one step window.

Reads `CUPTI_ACTIVITY_KIND_KERNEL` joined to `StringIds` (export with `nsys export --type sqlite`, or use the
`.sqlite` that `nsys stats` writes next to the report) and prints a markdown table of total ms, launch count,
mean and median ms per kernel, sorted by total.

Without `--step-boundary`, the whole capture is summed (dominated by warmup and autotuning). With it, steps are
delimited by clusters of kernels whose name matches the regex (e.g. `FusedAdamMathFunctor`, the fused AdamW
kernels that end each training step): clusters are split where consecutive matches are more than
`--cluster-gap-ms` apart, and step N runs from the end of cluster N-1 to the end of cluster N. `--step-index`
picks the step (default -1, the last).

Usage:
  python3 nsys_kernels.py report.sqlite --device 0 --step-boundary FusedAdamMathFunctor --top 20
  python3 nsys_kernels.py report.sqlite --group short --csv kernels.csv
"""

import argparse
import csv
import re
import sqlite3
import statistics
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sqlite")
    parser.add_argument("--device", type=int, default=None, help="deviceId to keep (default: all devices)")
    parser.add_argument("--step-boundary", default=None, help="regex for kernels that end each step")
    parser.add_argument("--cluster-gap-ms", type=float, default=100.0, help="gap that separates boundary clusters")
    parser.add_argument("--step-index", type=int, default=-1, help="which step window to keep")
    parser.add_argument("--group", choices=("demangled", "short"), default="demangled", help="kernel name column")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--name-width", type=int, default=80)
    parser.add_argument("--csv", default=None, help="also write every kernel to this CSV path")
    return parser.parse_args()


def load_kernels(path, device, group):
    column = "demangledName" if group == "demangled" else "shortName"
    query = (
        f"select s.value, k.start, k.end, k.deviceId from CUPTI_ACTIVITY_KIND_KERNEL k "
        f"join StringIds s on s.id = k.{column}"
    )
    rows = sqlite3.connect(path).execute(query).fetchall()
    return [(name, start, end) for name, start, end, dev in rows if device is None or dev == device]


def step_window(kernels, boundary, gap_ns, index):
    pattern = re.compile(boundary)
    marks = sorted((start, end) for name, start, end in kernels if pattern.search(name))
    if not marks:
        raise SystemExit(f"no kernel matches --step-boundary {boundary!r}")
    cluster_ends = [end for (_, end), (next_start, _) in zip(marks, marks[1:] + [(float("inf"), 0)]) if next_start - end > gap_ns]
    if len(cluster_ends) < 2:
        raise SystemExit(f"found {len(cluster_ends)} boundary cluster(s); need at least 2 to form a step")
    starts, ends = cluster_ends[:-1], cluster_ends[1:]
    return starts[index], ends[index]


def main():
    args = parse_args()
    kernels = load_kernels(args.sqlite, args.device, args.group)
    if args.step_boundary:
        lo, hi = step_window(kernels, args.step_boundary, args.cluster_gap_ms * 1e6, args.step_index)
        kernels = [k for k in kernels if k[1] > lo and k[2] <= hi]
        print(f"step window {(hi - lo) / 1e6:.1f} ms ({len(kernels)} kernels)")
    durations = defaultdict(list)
    for name, start, end in kernels:
        durations[name].append((end - start) / 1e6)
    rows = sorted(
        ((name, sum(d), len(d), statistics.mean(d), statistics.median(d)) for name, d in durations.items()),
        key=lambda row: -row[1],
    )
    total = sum(row[1] for row in rows)
    print(f"| {'kernel':<{args.name_width}} | total ms | share | count | mean ms | median ms |")
    print(f"|{'-' * (args.name_width + 2)}|---------:|------:|------:|--------:|----------:|")
    for name, tot, count, mean, median in rows[: args.top]:
        short = name if len(name) <= args.name_width else name[: args.name_width - 3] + "..."
        print(f"| {short:<{args.name_width}} | {tot:8.1f} | {100 * tot / total:4.1f}% | {count:5d} | {mean:7.3f} | {median:9.3f} |")
    print(f"total kernel time {total:.1f} ms")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["kernel", "total_ms", "count", "mean_ms", "median_ms"])
            writer.writerows(rows)
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
