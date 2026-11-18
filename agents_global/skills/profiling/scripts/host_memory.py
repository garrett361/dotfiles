# /// script
# requires-python = ">=3.10"
# ///
"""Summarize host memory sample logs: peak used memory, shared memory and locked memory of a node during a run.

Answers "how much host RAM did this run (or one phase of it) take, against the node's idle level?", e.g. pinned
staging buffers, offloaded activations or page cache from checkpoint writes. Each input is one CSV log, optionally
labeled `LABEL=path`, with a header row: `time` (epoch seconds) and `/proc/meminfo` fields in kB (at least `MemTotal`
and `MemAvailable`; `Shmem`, `Mlocked`, `Cached`, `Dirty` and `Writeback` are reported when present). A logger that
writes this format, one line per interval:

    fields=(MemTotal MemAvailable Shmem Cached Dirty Writeback Mlocked); (IFS=,; echo "time,${fields[*]}")
    while true; do awk -v t="$(date +%s.%N)" -v want="${fields[*]}" 'BEGIN {n = split(want, o, " ")}
      {sub(":", "", $1); kb[$1] = $2} END {l = t; for (i = 1; i <= n; i++) l = l "," kb[o[i]]; print l}' /proc/meminfo
      sleep 0.5; done > host_memory.csv

Used memory is `MemTotal - MemAvailable` (page cache the kernel can drop does not count). Per log it prints the
number of samples, the baseline (median used over the first `--baseline-s` seconds, default 5, before the run
allocates), and the peak of used, `Shmem` (includes shared anonymous mappings such as page-locked `mmap` buffers),
`Mlocked`, `Cached` and `Dirty + Writeback`, each in GiB with its time offset from the log's start; and the peak used
above the baseline. `--window NAME=START,END` (repeatable; epoch seconds, or offsets from the log's start when both
are below 1e6) adds the same peaks over that window, e.g. a checkpoint's staging or write. `--json PATH` writes
everything.

Usage: uv run --script host_memory.py [LABEL=]host_memory.csv [...] [--baseline-s 5] [--window NAME=START,END ...]
       [--json out.json]
"""

import argparse
import csv
import json
import statistics

KIB_PER_GIB = 2**20
PEAK_FIELDS = ["used", "Shmem", "Mlocked", "Cached", "dirty_writeback"]


def read_log(path: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                sample = {key: float(value) for key, value in row.items() if value not in (None, "")}
            except ValueError:
                continue
            if "MemTotal" not in sample or "MemAvailable" not in sample:
                continue
            sample["used"] = sample["MemTotal"] - sample["MemAvailable"]
            if "Dirty" in sample and "Writeback" in sample:
                sample["dirty_writeback"] = sample["Dirty"] + sample["Writeback"]
            rows.append(sample)
    return rows


def peaks(samples: list[dict], t0: float) -> dict:
    out = {}
    for field in PEAK_FIELDS:
        present = [s for s in samples if field in s]
        if present:
            top = max(present, key=lambda s: s[field])
            out[field] = {"gib": top[field] / KIB_PER_GIB, "at_s": top["time"] - t0}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("logs", nargs="+", help="[LABEL=]path of a CSV log")
    p.add_argument("--baseline-s", type=float, default=5.0, help="seconds at the log's start for the baseline")
    p.add_argument("--window", action="append", default=[], metavar="NAME=START,END")
    p.add_argument("--json", default=None)
    args = p.parse_args()

    result = {}
    for spec in args.logs:
        label, path = spec.split("=", 1) if "=" in spec else (spec, spec)
        samples = read_log(path)
        if not samples:
            print(f"{label}: no samples")
            continue
        t0 = samples[0]["time"]
        baseline = statistics.median(s["used"] for s in samples if s["time"] - t0 <= args.baseline_s)
        entry = {"path": path, "samples": len(samples), "span_s": samples[-1]["time"] - t0,
                 "baseline_used_gib": baseline / KIB_PER_GIB, "peaks": peaks(samples, t0), "windows": {}}
        entry["peak_above_baseline_gib"] = entry["peaks"]["used"]["gib"] - entry["baseline_used_gib"]
        for window in args.window:
            name, bounds = window.split("=", 1)
            start, end = (float(x) for x in bounds.split(","))
            if start < 1e6 and end < 1e6:
                start, end = start + t0, end + t0
            inside = [s for s in samples if start <= s["time"] <= end]
            entry["windows"][name] = {"samples": len(inside), "peaks": peaks(inside, t0) if inside else {}}
        result[label] = entry

        print(f"## {label} ({path}): {entry['samples']} samples over {entry['span_s']:.0f} s\n")
        print("| window | samples | " + " | ".join(f"peak {f} GiB (at s)" for f in PEAK_FIELDS) + " |")
        print("|---|---|" + "---|" * len(PEAK_FIELDS))
        rows = [("whole log", entry["samples"], entry["peaks"])]
        rows += [(name, w["samples"], w["peaks"]) for name, w in entry["windows"].items()]
        for name, count, pk in rows:
            cells = " | ".join(f"{pk[f]['gib']:.1f} ({pk[f]['at_s']:.0f})" if f in pk else "-" for f in PEAK_FIELDS)
            print(f"| {name} | {count} | {cells} |")
        print(f"\nbaseline used {entry['baseline_used_gib']:.1f} GiB (median of the first {args.baseline_s:g} s); "
              f"peak used above it {entry['peak_above_baseline_gib']:.1f} GiB\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
