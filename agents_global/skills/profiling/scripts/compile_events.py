# /// script
# requires-python = ">=3.10"
# ///
"""Place every rank's torch.compile recompiles and every node's DeepGEMM JIT compiles in the training step they stalled.

Reads one prime-rl run directory (the one holding `monitors/file/metrics.jsonl` and `logs/`):
- Steps: each `time/step` record in metrics.jsonl; its `time` is the step's end (epoch seconds), so step k spans
  (end of step k-1, end of step k].
- Dynamo: every `Recompiling function` record in every rank's torchrun log under `logs/attempt_N/trainer/`, run with
  `TORCH_LOGS=recompiles`. The rank comes from torch's `[rankR]:` prefix and the time from the glog timestamp
  (`V1019 19:49:02.48`, local time; the year is taken from the first step).
- DeepGEMM: `deep_gemm_cache_<host>.txt` files anywhere under `logs/attempt_N/`, one line per cache entry,
  `<mtime epoch seconds> <entry name>`, e.g. written after training by
  `find $DG_JIT_CACHE_DIR/cache -mindepth 1 -maxdepth 1 -printf "%T@ %f\n"`. Each entry's mtime is when that node
  first compiled the kernel.

Prints a markdown table per step with any event (step time, Dynamo recompiles with their ranks, DeepGEMM compiles with
their nodes), then `last compile step: K` over all events. Pass K + 1 as the start of `run_metrics.py --steady` to
report steady-state step time after every compile. `--events-csv` writes one row per event: kind, step, time, where
(rank or host), what (function and first guard failure, or kernel entry).

Usage:
  uv run --script compile_events.py <run dir>
  uv run --script compile_events.py <run dir> --attempt 1 --events-csv events.csv
"""

import argparse
import csv
import json
import re
import time
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

RECOMPILE = re.compile(r"\[rank(\d+)\]:[VIWE](\d{4}) (\d\d:\d\d:\d\d\.\d+) .*\[__recompiles\] Recompiling function (\S+)")
REASON = re.compile(r"\[__recompiles\]\s+- \d+/\d+: (.*)")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--events-csv", type=Path, default=None)
    return parser.parse_args()


def load_steps(run_dir: Path) -> list[tuple[int, float, float]]:
    """(step, end epoch seconds, step seconds), sorted by step."""
    steps = {}
    for line in (run_dir / "monitors" / "file" / "metrics.jsonl").open():
        record = json.loads(line)
        if "time/step" in record:
            steps[record["step"]] = (record["time"], record["time/step"])
    return [(step, end, seconds) for step, (end, seconds) in sorted(steps.items())]


def glog_epoch(mmdd: str, clock: str, year: int) -> float:
    whole, _, fraction = clock.partition(".")
    struct = time.strptime(f"{year}{mmdd} {whole}", "%Y%m%d %H:%M:%S")
    return time.mktime(struct) + float(f"0.{fraction}")


def dynamo_events(log_dir: Path, year: int) -> list[tuple[float, str, str]]:
    """(epoch seconds, rank, function: first guard failure) per recompile, deduplicated across tee'd copies."""
    events = set()
    for log in sorted(log_dir.rglob("*.log")):
        pending = None
        for line in log.open(errors="replace"):
            if match := RECOMPILE.search(line):
                pending = (glog_epoch(match.group(2), match.group(3), year), f"rank{match.group(1)}", match.group(4))
            elif pending and (match := REASON.search(line)):
                events.add((pending[0], pending[1], f"{pending[2]}: {match.group(1).split('  #')[0].strip()}"))
                pending = None
    return sorted(events)


def deepgemm_events(log_dir: Path) -> list[tuple[float, str, str]]:
    events = []
    for listing in sorted(log_dir.rglob("deep_gemm_cache_*.txt")):
        host = listing.stem.removeprefix("deep_gemm_cache_")
        for line in listing.open():
            mtime, _, entry = line.strip().partition(" ")
            if entry.startswith("kernel."):
                events.append((float(mtime), host, entry))
    return sorted(events)


def main():
    args = parse_args()
    steps = load_steps(args.run_dir)
    ends = [end for _, end, _ in steps]
    year = time.localtime(ends[0]).tm_year
    log_dir = args.run_dir / "logs" / f"attempt_{args.attempt}"

    def step_of(epoch: float) -> int:
        return steps[min(bisect_left(ends, epoch), len(steps) - 1)][0]

    events = [("dynamo", *e) for e in dynamo_events(log_dir / "trainer", year)]
    events += [("deepgemm", *e) for e in deepgemm_events(log_dir)]
    by_step: dict[int, dict[str, list[str]]] = defaultdict(lambda: {"dynamo": [], "deepgemm": []})
    rows = []
    for kind, epoch, where, what in events:
        step = step_of(epoch)
        by_step[step][kind].append(where)
        rows.append((kind, step, f"{epoch:.3f}", where, what))

    seconds = {step: s for step, _, s in steps}
    print("| step | step time (s) | Dynamo recompiles | ranks | DeepGEMM compiles | nodes |")
    print("|---:|---:|---:|---|---:|---|")
    for step in sorted(by_step):
        dynamo, deepgemm = by_step[step]["dynamo"], by_step[step]["deepgemm"]
        ranks = ",".join(sorted(set(dynamo), key=lambda r: int(r[4:])))
        nodes = ",".join(sorted(set(deepgemm)))
        print(f"| {step} | {seconds[step]:.2f} | {len(dynamo)} | {ranks} | {len(deepgemm)} | {nodes} |")
    print(f"\n{len(steps)} steps, {sum(k == 'dynamo' for k, *_ in rows)} Dynamo recompiles, "
          f"{sum(k == 'deepgemm' for k, *_ in rows)} DeepGEMM compiles")
    print(f"last compile step: {max(by_step) if by_step else 0}")

    if args.events_csv:
        with args.events_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["kind", "step", "epoch", "where", "what"])
            writer.writerows(sorted(rows, key=lambda r: (r[1], r[0], r[3])))


if __name__ == "__main__":
    main()
