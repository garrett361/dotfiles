# /// script
# requires-python = ">=3.10"
# ///
"""Where a thread's wall time went, and when, from stack_sampler/sitecustomize.py samples (host side, no profiler).

Input: one or more `stacks_rank<R>.txt` files (`<unix time>\\t<thread> (<tid>)\\t<frame>;...`, outermost first).
Each sample of the kept threads (`--thread REGEX`, default `MainThread`) gets the label of the first `--group
LABEL:REGEX` (repeatable, in order) that matches any of its frames, else `other: <leaf function>` (or the deepest
frame matching `--leaf-filter REGEX` when given, to skip library frames). A sample counts 1/HZ seconds, HZ being the
median sampling rate in the file (or `--hz`).

Prints, per file: seconds per label over the window, then a timeline of `--bucket` seconds with the top labels in
each bucket. `--window START END` keeps samples between those seconds after the file's first sample (or between
absolute unix times when both exceed 1e9). `--marks NAME=UNIX_TIME` (repeatable) prints each mark's offset, for
lining up phases logged elsewhere. `--collapsed PATH` writes the window's stacks in py-spy raw format
(`thread;frame;... COUNT`) for pyspy_frames.py `--focus`.

Usage: uv run --script stack_timeline.py stacks_rank0.txt [--thread MainThread] [--window 300 600] [--bucket 10]
       [--group "deepgemm jit:deep_gemm" --group "triton compile:triton/compiler"] [--top 12] [--collapsed out.txt]
"""

import argparse
import re
import statistics
from collections import Counter, defaultdict


def read_samples(path, thread_re):
    samples = []
    with open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3 or not thread_re.search(parts[1]):
                continue
            samples.append((float(parts[0]), parts[1], parts[2].split(";")))
    return samples


def label_of(frames, groups, leaf_filter):
    for label, pattern in groups:
        if any(pattern.search(frame) for frame in frames):
            return label
    if leaf_filter is not None:
        for frame in reversed(frames):
            if leaf_filter.search(frame):
                return f"other: {frame}"
    return f"other: {frames[-1] if frames else '?'}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--thread", default="MainThread", help="REGEX over thread names to keep")
    parser.add_argument("--group", action="append", default=[], help="LABEL:REGEX over frames, first match wins")
    parser.add_argument("--leaf-filter", default=None, help="REGEX: label unmatched samples by the deepest such frame")
    parser.add_argument("--window", nargs=2, type=float, default=None)
    parser.add_argument("--bucket", type=float, default=10.0, help="timeline bucket in seconds (0: no timeline)")
    parser.add_argument("--top", type=int, default=12, help="labels in the summary")
    parser.add_argument("--per-bucket", type=int, default=3, help="labels per timeline bucket")
    parser.add_argument("--hz", type=float, default=None, help="sampling rate (default: from the timestamps)")
    parser.add_argument("--marks", action="append", default=[], help="NAME=UNIX_TIME")
    parser.add_argument("--collapsed", default=None, help="write the window's stacks in py-spy raw format")
    args = parser.parse_args()

    thread_re = re.compile(args.thread)
    groups = [(g.split(":", 1)[0], re.compile(g.split(":", 1)[1])) for g in args.group]
    leaf_filter = re.compile(args.leaf_filter) if args.leaf_filter else None
    collapsed = Counter()
    for path in args.files:
        samples = read_samples(path, thread_re)
        if not samples:
            print(f"{path}: no samples of threads matching {args.thread!r}")
            continue
        t0 = samples[0][0]
        times = sorted({t for t, _, _ in samples})
        hz = args.hz or 1.0 / statistics.median(b - a for a, b in zip(times, times[1:]))
        if args.window is not None:
            start, end = args.window
            if start < 1e9 or end < 1e9:
                start, end = t0 + start, t0 + end
            samples = [s for s in samples if start <= s[0] <= end]
        print(f"== {path}: {len(samples)} samples at {hz:.1f} Hz, first sample at unix {t0:.3f}")
        for mark in args.marks:
            name, _, value = mark.partition("=")
            print(f"   mark {name}: {float(value) - t0:+.1f} s")
        totals = Counter()
        timeline = defaultdict(Counter)
        for t, thread, frames in samples:
            label = label_of(frames, groups, leaf_filter)
            totals[label] += 1
            if args.bucket > 0:
                timeline[int((t - t0) // args.bucket)][label] += 1
            collapsed[";".join([thread.split(" (")[0], *frames])] += 1
        total_s = sum(totals.values()) / hz
        print(f"{'seconds':>9} {'share':>6}  label  (window total {total_s:.1f} s)")
        for label, count in totals.most_common(args.top):
            print(f"{count / hz:9.1f} {count / sum(totals.values()):6.1%}  {label}")
        if args.bucket > 0:
            print(f"timeline ({args.bucket:g} s buckets, seconds after the first sample):")
            for bucket in sorted(timeline):
                counts = timeline[bucket]
                parts = ", ".join(
                    f"{label} {count / hz:.1f}s" for label, count in counts.most_common(args.per_bucket)
                )
                print(f"  {bucket * args.bucket:7.0f}  {parts}")
    if args.collapsed:
        with open(args.collapsed, "w") as out:
            for stack, count in collapsed.items():
                out.write(f"{stack} {count}\n")


if __name__ == "__main__":
    main()
