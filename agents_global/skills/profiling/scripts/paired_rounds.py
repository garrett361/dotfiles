# /// script
# requires-python = ">=3.10"
# dependencies = ["scipy"]
# ///
"""Paired step-time comparison of arms run in interleaved rounds on the same hosts, with the round as the unit.

Each run is a prime-rl run directory (`<run>/monitors/file/metrics.jsonl`, records merged by `step`) or a `.jsonl`
file with a `step` key. `--steps LO HI` picks the counted steps (inclusive) and `--metric` the per-step value
(default `time/step`); records written by several processes can be narrowed with `--row-filter KEY=VALUE`.

Pilot (`--pilot RUN_A RUN_B`, two runs of the same arm and code): per counted step the difference A - B, reported
as the run-to-run offset (mean difference), its standard deviation, the lag-1 autocorrelation of the differences,
the effective number of independent steps n (1 - r1) / (1 + r1), and the standard error of the offset from it. The
run means' difference is what a round's paired difference contains as noise, so `--target-se MS` adds the number
of rounds whose mean difference reaches that standard error, taking one pilot offset as one round's noise (a lower
bound on rounds: repeat pilots for a spread).

Rounds (`--round NAME:ARM=RUN,ARM=RUN,...`, repeatable, `--reference ARM`): per run the mean of the metric over the
counted steps, per round each arm's difference from the reference arm's run of that round, then per arm the mean
over rounds, its standard deviation, and the 95% interval from Student's t with rounds - 1 degrees of freedom, in
milliseconds and as a percentage of the reference arm's mean step time (the base). `--json OUT` writes everything.

Usage:
  uv run --script paired_rounds.py --steps 11 60 --pilot runs/base-p1 runs/base-p2 --target-se 2
  uv run --script paired_rounds.py --steps 11 60 --reference baseline \\
    --round 1:baseline=runs/b1,fixed=runs/f1 --round 2:baseline=runs/b2,fixed=runs/f2
"""

import argparse
import itertools
import json
import math
import statistics
from pathlib import Path

from scipy import stats


def load(run: str, metric: str, lo: int, hi: int, filters: list[tuple[str, str]]) -> dict[int, float]:
    path = Path(run)
    if path.is_dir():
        path = path / "monitors" / "file" / "metrics.jsonl"
    values = {}
    for line in path.open():
        record = json.loads(line)
        step = record.get("step")
        if step is None or not lo <= step <= hi or metric not in record:
            continue
        if all(str(record.get(key)) == value for key, value in filters):
            values[step] = float(record[metric])
    missing = [step for step in range(lo, hi + 1) if step not in values]
    if missing:
        raise SystemExit(f"{run}: no {metric} at steps {missing}")
    return values


def lag1(values: list[float]) -> float:
    mean = statistics.fmean(values)
    centered = [v - mean for v in values]
    denominator = sum(c * c for c in centered)
    return sum(a * b for a, b in itertools.pairwise(centered)) / denominator if denominator else 0.0


def pilot(args) -> dict:
    a, b = (load(run, args.metric, args.steps[0], args.steps[1], args.row_filter) for run in args.pilot)
    diffs = [(a[step] - b[step]) * 1000 for step in sorted(a)]
    r1 = lag1(diffs)
    n_eff = min(len(diffs), len(diffs) * (1 - r1) / (1 + r1)) if r1 < 1 else 1.0
    sd = statistics.stdev(diffs)
    out = {
        "runs": args.pilot,
        "steps": len(diffs),
        "mean_a_ms": statistics.fmean(a.values()) * 1000,
        "mean_b_ms": statistics.fmean(b.values()) * 1000,
        "offset_ms": statistics.fmean(diffs),
        "sd_step_diff_ms": sd,
        "lag1_autocorrelation": r1,
        "effective_steps": n_eff,
        "se_offset_ms": sd / math.sqrt(max(n_eff, 1.0)),
    }
    if args.target_se:
        out["rounds_for_target_se"] = math.ceil((abs(out["offset_ms"]) / args.target_se) ** 2)
    print("| quantity | value |\n|---|---:|")
    for key, value in out.items():
        print(f"| {key} | {value if isinstance(value, (int, list)) else f'{value:.4f}'} |")
    return out


def rounds(args) -> dict:
    lo, hi = args.steps
    table = {}
    for spec in args.round:
        name, _, arms = spec.partition(":")
        table[name] = {
            arm: statistics.fmean(load(run, args.metric, lo, hi, args.row_filter).values()) * 1000
            for arm, _, run in (item.partition("=") for item in arms.split(","))
        }
    base = statistics.fmean(row[args.reference] for row in table.values())
    arms = sorted({arm for row in table.values() for arm in row} - {args.reference})
    out = {"reference": args.reference, "base_ms": base, "rounds": table, "arms": {}}
    print(f"base: {args.reference} mean step {base:.2f} ms over {len(table)} rounds\n")
    print("| arm | rounds | mean diff (ms) | sd (ms) | 95% interval (ms) | mean diff (% of base) | 95% interval (% of base) |")
    print("|---|---:|---:|---:|---|---:|---|")
    for arm in arms:
        diffs = [row[arm] - row[args.reference] for row in table.values() if arm in row and args.reference in row]
        mean = statistics.fmean(diffs)
        sd = statistics.stdev(diffs) if len(diffs) > 1 else float("nan")
        half = stats.t.ppf(0.975, len(diffs) - 1) * sd / math.sqrt(len(diffs)) if len(diffs) > 1 else float("nan")
        out["arms"][arm] = {"diffs_ms": diffs, "mean_ms": mean, "sd_ms": sd, "ci_ms": [mean - half, mean + half],
                            "mean_pct": 100 * mean / base, "ci_pct": [100 * (mean - half) / base, 100 * (mean + half) / base]}
        print(f"| {arm} | {len(diffs)} | {mean:.2f} | {sd:.2f} | [{mean - half:.2f}, {mean + half:.2f}] | "
              f"{100 * mean / base:.3f} | [{100 * (mean - half) / base:.3f}, {100 * (mean + half) / base:.3f}] |")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--steps", type=int, nargs=2, required=True, metavar=("LO", "HI"))
    parser.add_argument("--metric", default="time/step")
    parser.add_argument("--row-filter", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--pilot", nargs=2, metavar=("RUN_A", "RUN_B"))
    parser.add_argument("--target-se", type=float, default=None, help="target standard error in ms (pilot)")
    parser.add_argument("--round", action="append", default=[], metavar="NAME:ARM=RUN,...")
    parser.add_argument("--reference", default="baseline")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    args.row_filter = [tuple(spec.split("=", 1)) for spec in args.row_filter]
    if not args.pilot and not args.round:
        parser.error("give --pilot or --round")
    out = {}
    if args.pilot:
        out["pilot"] = pilot(args)
    if args.round:
        out["rounds"] = rounds(args)
    if args.json:
        args.json.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
