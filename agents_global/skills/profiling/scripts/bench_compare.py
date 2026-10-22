# /// script
# requires-python = ">=3.10"
# ///
"""Join `bench_ops.py --csv` files from several runs (arms, sessions) into one markdown table per label.

Answers "how did this op's time move between two code versions, and did the reference stay put?" when the same
CASES.py was run once per arm. Each input is `ARM=path.csv` (or `ARM=a.csv,b.csv` to pool several runs of one arm
that cover different cases; a later file wins on a repeated case); rows are joined on (case, label). For every label kept
(`--label REGEX`, default all), each case gets one row with each arm's median and, with `--spread`, its p20 to p80.
`--ref-label NAME` adds, per arm, the ratio of that label's median in the same CSV to this label's median (above 1x
means faster than the reference within that run, so a ratio survives clock drift between sessions); `--ref-label
first` uses each case's first label (bench_ops.py's own ratio reference). The last column
is the first arm's median divided by the last arm's (above 1x means the last arm is faster). `--case REGEX` keeps
matching cases.

Usage: uv run --script bench_compare.py OLD=a.csv NEW=b.csv [MORE=c.csv ...] [--label triton]
       [--ref-label torch._grouped_mm] [--case REGEX] [--spread] [--decimals 3]
"""

import argparse
import csv
import re


def read_csv(paths):
    rows = {}
    for path in paths.split(","):
        with open(path, newline="") as f:
            rows.update({(r["case"], r["label"]): r for r in csv.DictReader(f)})
    return rows


def first_label(rows, case):
    return next((lab for c, lab in rows if c == case), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arms", nargs="+", help="ARM=path to a bench_ops.py --csv file")
    parser.add_argument("--label", default=".*", help="regex over labels to report")
    parser.add_argument("--ref-label", help="label whose median each arm's median is divided into, per CSV")
    parser.add_argument("--case", default=".*", help="regex over case names to report")
    parser.add_argument("--spread", action="store_true", help="show p20 to p80 next to each median")
    parser.add_argument("--decimals", type=int, default=3)
    args = parser.parse_args()

    arms = []
    for spec in args.arms:
        name, _, path = spec.partition("=")
        arms.append((name, read_csv(path)))
    first_rows = arms[0][1]
    label_re, case_re = re.compile(args.label), re.compile(args.case)
    labels = [lab for lab in dict.fromkeys(lab for _, lab in first_rows) if label_re.search(lab)]
    cases = [c for c in dict.fromkeys(c for c, _ in first_rows) if case_re.search(c)]
    fmt = f"{{:.{args.decimals}f}}"

    def cell(row):
        if row is None:
            return "-"
        text = fmt.format(float(row["median_ms"]))
        if args.spread:
            text += f" ({fmt.format(float(row['p20_ms']))} to {fmt.format(float(row['p80_ms']))})"
        return text

    for label in labels:
        header = ["case"]
        for name, _ in arms:
            header.append(f"{name} {label} ms")
            if args.ref_label and label != args.ref_label:
                header.append(f"{name} {args.ref_label} / {label}")
        header.append(f"{arms[0][0]} / {arms[-1][0]}")
        print(f"\n### {label}\n")
        print("| " + " | ".join(header) + " |")
        print("|---|" + "---:|" * (len(header) - 1))
        for case in cases:
            row = [case]
            medians = []
            for _, rows in arms:
                r = rows.get((case, label))
                row.append(cell(r))
                medians.append(float(r["median_ms"]) if r else None)
                if args.ref_label and label != args.ref_label:
                    ref_label = first_label(rows, case) if args.ref_label == "first" else args.ref_label
                    ref = rows.get((case, ref_label)) if ref_label != label else None
                    row.append(f"{float(ref['median_ms']) / float(r['median_ms']):.2f}x" if ref and r else "-")
            if all(m is not None for m in (medians[0], medians[-1])):
                row.append(f"{medians[0] / medians[-1]:.2f}x")
            else:
                row.append("-")
            if any(m is not None for m in medians):
                print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
