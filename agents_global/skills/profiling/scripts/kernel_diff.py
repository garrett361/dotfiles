"""Print a markdown table of per-kernel time changes between two `top_kernels.py --csv` files.

Rows are joined on the raw kernel name (`kernel_names` column) within each group (`compute` / `nccl`), so labels
that shorten alike in each table still match. Ranks by absolute change in total time; kernels present in only one
file show 0 on the other side. `--category LABEL:REGEX` (repeatable, ordered, first match wins, raw names) adds a
per-category before/after/delta table; unmatched kernels fall into "other".

`--key label` joins on the `label` column instead, which for `top_kernels.py --by site` or `--by both` CSVs is the
launching op (with dims) plus the kernel, so the same kernel launched from different ops (forward vs backward, or a
cast inside a custom op vs one in a compiled graph) gets its own row; categories then match the label too.
`--filter REGEX` keeps only rows whose key matches (e.g. one kernel family across all its call sites).

Usage: python3 kernel_diff.py before.csv after.csv [--top 30] [--name-width 90] [--group compute]
       [--category "expert GEMM:sm90_fp8_gemm_1d"] [--before-label A] [--after-label B] [--key label] [--filter REGEX]
"""

import argparse
import csv
import re


def load(path, group, column="kernel_names", keep=None):
    rows = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if group != "all" and row["group"] != group:
                continue
            if keep is not None and not keep.search(row[column]):
                continue
            key = (row["group"], row[column])
            total, calls = rows.get(key, (0.0, 0))
            rows[key] = (total + float(row["total_us"]) / 1000.0, calls + int(row["calls"]))
    return rows


def shorten(name, width):
    return name if len(name) <= width else name[: width - 3] + "..."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--name-width", type=int, default=90)
    parser.add_argument("--group", default="compute", help="'compute', 'nccl', or 'all'")
    parser.add_argument("--category", action="append", default=[], metavar="LABEL:REGEX")
    parser.add_argument("--before-label", default="before")
    parser.add_argument("--after-label", default="after")
    parser.add_argument("--key", choices=("kernel", "label"), default="kernel", help="join on raw kernel names or labels")
    parser.add_argument("--filter", default=None, help="keep only rows whose key matches this regex")
    args = parser.parse_args()

    column = "kernel_names" if args.key == "kernel" else "label"
    keep = re.compile(args.filter) if args.filter else None
    before, after = load(args.before, args.group, column, keep), load(args.after, args.group, column, keep)
    keys = set(before) | set(after)
    rows = []
    for key in keys:
        b_ms, b_calls = before.get(key, (0.0, 0))
        a_ms, a_calls = after.get(key, (0.0, 0))
        rows.append((a_ms - b_ms, b_ms, a_ms, b_calls, a_calls, key))
    rows.sort(key=lambda r: -abs(r[0]))

    b_total = sum(v[0] for v in before.values())
    a_total = sum(v[0] for v in after.values())
    print(f"# Kernel time diff ({args.group}): {args.before_label} -> {args.after_label}\n")
    print(f"- summed kernel time: {b_total:.1f} ms -> {a_total:.1f} ms ({a_total - b_total:+.1f} ms)")
    print(f"- before: `{args.before}`\n- after: `{args.after}`\n")
    print(f"| # | {args.before_label} ms | {args.after_label} ms | delta ms | calls before | calls after | kernel |")
    print("|---|---|---|---|---|---|---|")
    for i, (delta, b_ms, a_ms, b_calls, a_calls, key) in enumerate(rows[: args.top], 1):
        print(f"| {i} | {b_ms:.1f} | {a_ms:.1f} | {delta:+.1f} | {b_calls} | {a_calls} | `{shorten(key[1], args.name_width)}` |")

    if args.category:
        rules = []
        for spec in args.category:
            label, regex = spec.split(":", 1)
            rules.append((label, re.compile(regex)))

        def categorize(name):
            return next((label for label, rx in rules if rx.search(name)), "other")

        labels = [label for label, _ in rules] + ["other"]
        sums = {label: [0.0, 0.0] for label in labels}
        for _, b_ms, a_ms, _, _, key in rows:
            entry = sums[categorize(key[1])]
            entry[0] += b_ms
            entry[1] += a_ms
        print(f"\n| category | {args.before_label} ms | {args.after_label} ms | delta ms |")
        print("|---|---|---|---|")
        for label in labels:
            b_ms, a_ms = sums[label]
            print(f"| {label} | {b_ms:.1f} | {a_ms:.1f} | {a_ms - b_ms:+.1f} |")


if __name__ == "__main__":
    main()
