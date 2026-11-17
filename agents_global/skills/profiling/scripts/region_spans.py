# /// script
# requires-python = ">=3.10"
# ///
"""Wall time of one model region (e.g. a MoE block) on the main compute stream, for traces without per-module ranges.

Under torch.compile a module often has no `record_function` range of its own, so its GPU time cannot be read from an
annotation. This script derives it from the kernels instead. Every kernel, memcpy and memset on the main stream (the
stream with the most non-`--comm` kernel time) is labeled from its `<host stack> [<dims>] : <kernel name>` text (the
`top_kernels.py --category-context` text): `inside` if it matches `--inside`, else `outside` if it matches
`--outside`, else neutral. A span starts at an inside activity and runs to the end of the last inside activity before
the next outside one; neutral activities and idle gaps between two inside activities belong to the span, those at a
span's edge do not. The region's wall time is the sum of its spans, so a region that the compiled graph interleaves
with other work (e.g. a shared expert scheduled between two norm kernels) still counts only its own stretches.

Per arm (`--trace LABEL=GLOB`, one file per rank, repeatable) it prints the whole-trace window (first to last GPU
activity on any stream), the region's wall time, its main-stream busy and idle time, and the window minus the region,
averaged over the files and divided by `--per` (e.g. the micro-steps one trace holds). With `--category LABEL:REGEX`
(first match wins, on the same text) it also splits main-stream busy time inside and outside the spans by category.
`--per-rank` prints each file's numbers; `--spans N` lists the first N spans of the first file (start, length, and
the tail of the first and last inside activity's text) to check the boundaries. `--csv` writes one row per arm and
quantity. Spans come from one traced step, so profiler host overhead inflates their idle time as it does the step's.

Usage: uv run --script region_spans.py --trace "bf16=traces/bf16/trace_[04].json.gz" [--trace ...] \\
         --inside 'prime_rl_ep::|router' --outside 'prime_rl_attn::|norm' [--comm 'nccl|NCCL'] [--per 6] \\
         [--category LABEL:REGEX ...] [--per-rank] [--spans 20] [--csv out.csv]
"""

import argparse
import csv
import glob
import re
import statistics
from collections import defaultdict

from trace_events import launch_context, launch_stacks, read_trace

GPU_CATEGORIES = ("kernel", "gpu_memcpy", "gpu_memset")


def analyse(path, inside, outside, comm, categories):
    events = read_trace(path)["traceEvents"]
    gpu = sorted((e for e in events if e.get("ph") == "X" and e.get("cat") in GPU_CATEGORIES), key=lambda e: e["ts"])
    per_stream = defaultdict(float)
    for e in gpu:
        if e.get("cat") == "kernel" and not comm.search(e["name"]):
            per_stream[(e["pid"], e["tid"])] += e["dur"]
    main = max(per_stream, key=per_stream.get)
    stream = [e for e in gpu if (e["pid"], e["tid"]) == main]
    stacks = launch_stacks(events, {e.get("args", {}).get("correlation") for e in stream})
    labels = []
    for e in stream:
        text = f"{launch_context(stacks.get(e.get('args', {}).get('correlation'), []))} : {e['name']}"
        side = "inside" if inside.search(text) else "outside" if outside.search(text) else "neutral"
        category = next((label for label, pattern in categories if pattern.search(text)), "other")
        labels.append((side, category, text))
    spans, open_at, last_inside = [], None, None
    for i, (e, (side, _, _)) in enumerate(zip(stream, labels)):
        if side == "inside":
            if open_at is None:
                open_at = i
            last_inside = i
        elif side == "outside" and open_at is not None:
            spans.append((open_at, last_inside))
            open_at = None
    if open_at is not None:
        spans.append((open_at, last_inside))
    in_span = [False] * len(stream)
    for first, last in spans:
        for i in range(first, last + 1):
            in_span[i] = True
    wall = sum(stream[last]["ts"] + stream[last]["dur"] - stream[first]["ts"] for first, last in spans)
    busy_in = sum(e["dur"] for e, flag in zip(stream, in_span) if flag)
    window = max(e["ts"] + e["dur"] for e in gpu) - min(e["ts"] for e in gpu)
    by_category = defaultdict(lambda: [0.0, 0.0])
    for e, flag, (_, category, _) in zip(stream, in_span, labels):
        by_category[category][0 if flag else 1] += e["dur"]
    listing = [
        (stream[first]["ts"] - stream[0]["ts"], stream[last]["ts"] + stream[last]["dur"] - stream[first]["ts"],
         labels[first][2], labels[last][2])
        for first, last in spans
    ]
    return {
        "window": window, "wall": wall, "busy": busy_in, "idle": wall - busy_in, "rest": window - wall,
        "spans": len(spans), "categories": by_category, "listing": listing,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", action="append", required=True, help="LABEL=GLOB of per-rank chrome traces")
    parser.add_argument("--inside", required=True, help="regex of the region's activities")
    parser.add_argument("--outside", required=True, help="regex of activities that end a span")
    parser.add_argument("--comm", default=r"nccl|NCCL", help="kernels ignored when picking the main stream")
    parser.add_argument("--category", action="append", default=[], metavar="LABEL:REGEX")
    parser.add_argument("--per", type=float, default=1.0, help="divide every time by this (e.g. micro-steps per trace)")
    parser.add_argument("--per-rank", action="store_true")
    parser.add_argument("--spans", type=int, default=0, help="list this many spans of each arm's first file")
    parser.add_argument("--csv", default=None)
    args = parser.parse_args()
    inside, outside, comm = re.compile(args.inside), re.compile(args.outside), re.compile(args.comm)
    categories = [(label, re.compile(regex)) for label, _, regex in (c.partition(":") for c in args.category)]
    scale = 1e3 * args.per
    keys = ("window", "wall", "busy", "idle", "rest")
    names = {"window": "whole-trace window", "wall": "region wall time (sum of spans)",
             "busy": "  main stream busy in spans", "idle": "  main stream idle in spans",
             "rest": "window minus region"}
    arms = {}
    for spec in args.trace:
        label, _, pattern = spec.partition("=")
        files = sorted(glob.glob(pattern))
        if not files:
            raise SystemExit(f"{label}: no files match {pattern}")
        arms[label] = [(path, analyse(path, inside, outside, comm, categories)) for path in files]
    labels = list(arms)
    print(f"inside: `{args.inside}`  \noutside: `{args.outside}`  \nms per {args.per:g} (`--per`), mean over files\n")
    print("| quantity | " + " | ".join(labels) + (" | delta |" if len(labels) == 2 else " |"))
    print("|---|" + "---:|" * (len(labels) + (len(labels) == 2)))
    means = {label: {k: statistics.mean(r[k] for _, r in runs) / scale for k in keys} for label, runs in arms.items()}
    for k in keys:
        cells = [f"{means[label][k]:.3f}" for label in labels]
        if len(labels) == 2:
            cells.append(f"{means[labels[1]][k] - means[labels[0]][k]:+.3f}")
        print(f"| {names[k]} | " + " | ".join(cells) + " |")
    print("| spans per file | " + " | ".join(str(arms[label][0][1]["spans"]) for label in labels)
          + (" | |" if len(labels) == 2 else " |"))
    if categories:
        print("\n## Main-stream busy time by category, inside / outside the spans\n")
        print("| category | " + " | ".join(f"{label} in | {label} out" for label in labels) + " |")
        print("|---|" + "---:|---:|" * len(labels))
        for category in [label for label, _ in categories] + ["other"]:
            cells = []
            for label in labels:
                runs = arms[label]
                for side in (0, 1):
                    cells.append(f"{statistics.mean(r['categories'][category][side] for _, r in runs) / scale:.3f}")
            print(f"| {category} | " + " | ".join(cells) + " |")
    if args.per_rank:
        print("\n## Per file\n")
        print("| arm | file | " + " | ".join(names[k].strip() for k in keys) + " | spans |")
        print("|---|---|" + "---:|" * (len(keys) + 1))
        for label, runs in arms.items():
            for path, r in runs:
                print(f"| {label} | {path.rsplit('/', 1)[-1]} | " + " | ".join(f"{r[k] / scale:.3f}" for k in keys)
                      + f" | {r['spans']} |")
    if args.spans:
        for label, runs in arms.items():
            print(f"\n## First {args.spans} spans of {label} ({runs[0][0].rsplit('/', 1)[-1]})\n")
            print("| start ms | length ms | first inside | last inside |")
            print("|---:|---:|---|---|")
            for start, length, first, last in runs[0][1]["listing"][: args.spans]:
                print(f"| {start / 1e3:.3f} | {length / 1e3:.3f} | {first[-110:]} | {last[-110:]} |")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["arm", "quantity", "ms"])
            for label in labels:
                for k in keys:
                    writer.writerow([label, k, f"{means[label][k]:.4f}"])


if __name__ == "__main__":
    main()
