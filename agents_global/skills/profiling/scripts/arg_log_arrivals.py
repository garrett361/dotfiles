# /// script
# requires-python = ">=3.10"
# ///
"""When each rank first (or at its Nth call) reached a function logged by `arg_log/`, and the arrival skew per group.

Reads `args_rank<R>.jsonl` from each ARG_LOG_DIR (one per run, as `arg_log/` writes them; every rank's `t_ns` is wall
time, so ranks on different nodes compare only as well as their clocks agree). For call index `--call` (default 0,
the first call), prints per rank the arrival time in seconds after the anchor (`--anchor-file`, a file whose mtime
marks the launch, e.g. a launcher's per-node marker; default the earliest arrival), and per group of `--group-size`
consecutive ranks (e.g. one expert-parallel group per node) the arrival skew, last minus first arrival, which is how
long the earliest rank of that group waits in a collective at that call. `--json OUT` writes the same numbers.

Usage:
  uv run --script arg_log_arrivals.py runs/a/arg_log [runs/b/arg_log ...] --group-size 8 \\
    --anchor-file task_host_0.txt [--call 0] [--json arrivals.json]
`--anchor-file` is resolved against each ARG_LOG_DIR's parent when relative.
"""

import argparse
import json
import re
from pathlib import Path


def arrivals(log_dir: Path, call: int) -> dict[int, int]:
    times = {}
    for path in log_dir.glob("args_rank*.jsonl"):
        rank = int(re.fullmatch(r"args_rank(\d+)\.jsonl", path.name).group(1))
        with path.open() as lines:
            for line in lines:
                record = json.loads(line)
                if record["call"] == call:
                    times[rank] = record["t_ns"]
                    break
    return times


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log_dirs", type=Path, nargs="+")
    parser.add_argument("--call", type=int, default=0)
    parser.add_argument("--group-size", type=int, default=8)
    parser.add_argument("--anchor-file", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    results = {}
    for log_dir in args.log_dirs:
        times = arrivals(log_dir, args.call)
        if not times:
            print(f"{log_dir}: no rank reached call {args.call}")
            continue
        if args.anchor_file is not None:
            anchor_path = args.anchor_file if args.anchor_file.is_absolute() else log_dir.parent / args.anchor_file
            anchor_ns = int(anchor_path.stat().st_mtime * 1e9)
            anchor_name = str(anchor_path)
        else:
            anchor_ns = min(times.values())
            anchor_name = "earliest arrival"
        ranks = sorted(times)
        groups = {}
        for start in range(0, max(ranks) + 1, args.group_size):
            members = [r for r in ranks if start <= r < start + args.group_size]
            if members:
                first = min(times[r] for r in members)
                last = max(times[r] for r in members)
                late = max(members, key=lambda r: times[r])
                groups[f"{start}-{start + args.group_size - 1}"] = {
                    "skew_s": (last - first) / 1e9,
                    "first_s": (first - anchor_ns) / 1e9,
                    "last_s": (last - anchor_ns) / 1e9,
                    "last_rank": late,
                    "ranks": len(members),
                }
        per_rank = {r: (times[r] - anchor_ns) / 1e9 for r in ranks}
        results[str(log_dir)] = {"anchor": anchor_name, "call": args.call, "groups": groups, "per_rank_s": per_rank}
        print(f"\n{log_dir} (call {args.call}, seconds after {anchor_name}, {len(ranks)} ranks)")
        print("| group | ranks | first | last | skew | last rank |")
        print("|---|---|---|---|---|---|")
        for name, g in groups.items():
            print(
                f"| {name} | {g['ranks']} | {g['first_s']:.2f} | {g['last_s']:.2f} | {g['skew_s']:.2f} | {g['last_rank']} |"
            )
        print("per rank: " + ", ".join(f"{r}: {s:.2f}" for r, s in per_rank.items()))
    if args.json is not None:
        args.json.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
