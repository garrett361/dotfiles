# /// script
# requires-python = ">=3.10"
# ///
"""Summarize hand-rolled phase timers printed from inside a kernel as `PREFIX key=value ...` lines.

Answers "where does each warp role spend its time" from per-warp `clock64` accumulators that a kernel `printf`s
once per launch (`tools/intra-kernel.md`, "CUDA C++: hand-rolled phase timers"). Each input is a log file or a glob
of them (one per rank, e.g. torchrun `--log-dir DIR --redirects 3`), optionally labeled `LABEL=path-or-glob` to put
several runs side by side. Every line containing `--prefix` (default `DGPROF`) is parsed from that token on into
`key=value` pairs; values that parse as numbers are fields, the rest are ignored unless used as keys.

Lines are grouped by `--by` keys (comma-separated, default `role`) and filtered with `--where key=value` (repeatable).
`--derive NAME=EXPR` (repeatable, applied in order) adds a per-line field computed from other fields with `+ - * /`,
parentheses and numbers, e.g. `--derive mma_dx=main_dx-full_dx`; a line missing a field the expression names, or
dividing by zero, gets no value for it. `--fields` keeps only fields matching its comma-separated globs (default every
numeric field except the `--by` keys). For each label, group and field the table gives the number of lines, the median,
p20 and p80 over lines, and the sum. With `--share TOTAL` it adds each field's share of TOTAL: the median over lines of
field/TOTAL, and the ratio of sums (sum of field over sum of TOTAL), which weights lines by their TOTAL.

Usage: uv run --script phase_timers.py [LABEL=]log-or-glob [...] [--prefix DGPROF] [--by role] [--where key=value]
       [--derive NAME=EXPR] [--fields GLOBS] [--share TOTAL] [--decimals 3] [--csv FILE]
"""

import argparse
import ast
import csv
import fnmatch
import glob
import operator
import statistics
import sys

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def number(text):
    try:
        return float(text)
    except ValueError:
        return None


def parse_line(line, prefix):
    pairs = {}
    for token in line[line.index(prefix) + len(prefix) :].split():
        if "=" in token:
            key, value = token.split("=", 1)
            pairs[key] = value
    return pairs


def evaluate(node, fields):
    if isinstance(node, ast.Expression):
        return evaluate(node.body, fields)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in fields:
            raise KeyError(node.id)
        return fields[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -evaluate(node.operand, fields)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](evaluate(node.left, fields), evaluate(node.right, fields))
    raise ValueError(f"unsupported expression element: {ast.dump(node)}")


def quantile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def sort_key(key):
    return tuple((0, float(x), "") if number(x) is not None else (1, 0.0, x) for x in key)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logs", nargs="+")
    parser.add_argument("--prefix", default="DGPROF")
    parser.add_argument("--by", default="role")
    parser.add_argument("--where", action="append", default=[])
    parser.add_argument("--derive", action="append", default=[])
    parser.add_argument("--fields")
    parser.add_argument("--share")
    parser.add_argument("--decimals", type=int, default=3)
    parser.add_argument("--csv")
    args = parser.parse_args()

    by = [k for k in args.by.split(",") if k]
    where = [w.split("=", 1) for w in args.where]
    derived = []
    for spec in args.derive:
        name, expr = spec.split("=", 1)
        derived.append((name, ast.parse(expr, mode="eval")))
    globs = args.fields.split(",") if args.fields else None

    groups = {}
    for spec in args.logs:
        label, pattern = spec.split("=", 1) if "=" in spec else (spec, spec)
        paths = sorted(glob.glob(pattern, recursive=True))
        if not paths:
            sys.exit(f"no file matches {pattern}")
        for path in paths:
            with open(path, errors="replace") as f:
                for line in f:
                    if args.prefix not in line:
                        continue
                    pairs = parse_line(line, args.prefix)
                    if any(pairs.get(k) != v for k, v in where) or any(k not in pairs for k in by):
                        continue
                    fields = {k: n for k, v in pairs.items() if k not in by and (n := number(v)) is not None}
                    for name, tree in derived:
                        try:
                            fields[name] = evaluate(tree, fields)
                        except (KeyError, ZeroDivisionError):
                            pass
                    groups.setdefault((label, *(pairs[k] for k in by)), []).append(fields)

    header = ["label", *by, "field", "lines", "median", "p20", "p80", "sum"]
    if args.share:
        header += [f"share_of_{args.share}_median", f"share_of_{args.share}_sum"]
    rows = []
    for key in sorted(groups, key=lambda k: (k[0], sort_key(k[1:]))):
        lines = groups[key]
        names = []
        for fields in lines:
            names += [n for n in fields if n not in names]
        if globs:
            names = [n for n in names if any(fnmatch.fnmatch(n, g) for g in globs)]
        for name in names:
            values = [fields[name] for fields in lines if name in fields]
            row = [*key, name, len(values), statistics.median(values), quantile(values, 0.2), quantile(values, 0.8)]
            row.append(sum(values))
            if args.share:
                pairs = [(f[name], f[args.share]) for f in lines if name in f and f.get(args.share)]
                total = sum(t for _, t in pairs)
                shares = [v / t for v, t in pairs]
                row.append(statistics.median(shares) if shares else None)
                row.append(sum(v for v, _ in pairs) / total if total else None)
            rows.append(row)

    def show(value):
        if isinstance(value, float):
            return f"{value:.{args.decimals}f}" if abs(value) < 1e6 else f"{value:.{args.decimals}e}"
        return "" if value is None else str(value)

    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for row in rows:
        print("| " + " | ".join(show(v) for v in row) + " |")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == "__main__":
    main()
