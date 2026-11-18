# /// script
# requires-python = ">=3.10"
# ///
"""Host time per Python function from py-spy raw (collapsed) stacks, per arm, untraced by torch.profiler.

Input: `py-spy record --threads --format raw` output, one file per arm (`--arm LABEL=PATH`, repeatable). Each line is
`thread (tid)[: name];frame;...;frame COUNT`, outermost frame first. Per arm it prints every thread's sample count and, for
the busiest `--threads N` threads, the functions with the most inclusive samples (a function counts once per stack).
`--group LABEL:REGEX` (repeatable) sums the stacks whose frames match REGEX into one row per arm, for named code
regions (e.g. one custom op's Python implementation). With two arms a delta column is added. `--focus REGEX` breaks down the stacks through the first frame matching
REGEX: the frames called directly from it and the leaf frames, by samples, per arm. `--thread REGEX` keeps only the
threads whose name matches (e.g. `MainThread`). Samples convert to ms with
`--rate` (Hz, py-spy's `--rate`) divided by `--steps` (iterations in the sampled window), if given; otherwise shares of
the thread's samples are printed. py-spy samples idle threads only with `--idle`, so without it a thread's samples are
its busy (GIL-holding or native) time.

Capture tip: a process can attach py-spy to itself under `ptrace_scope = 1` after
`prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)` (ctypes), by spawning `py-spy record --pid <own pid> --duration S` before
the window to sample.

Usage: uv run --script pyspy_frames.py --arm bf16=bf16.txt --arm fp8=fp8.txt [--threads 2] [--top 25]
       [--group "dgrad:down_fp8_backward"] [--rate 1000 --steps 40]
"""

import argparse
import re
from collections import Counter, defaultdict


def load(path):
    threads = Counter()
    inclusive = defaultdict(Counter)
    groups_raw = defaultdict(list)
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            stack, _, count = line.rpartition(" ")
            thread, *frames = stack.split(";")
            count = int(count)
            threads[thread] += count
            for frame in set(frames):
                inclusive[thread][frame] += count
            groups_raw[thread].append((frames, count))
    return threads, inclusive, groups_raw


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", action="append", required=True, help="LABEL=PATH of py-spy raw output")
    parser.add_argument("--threads", type=int, default=2, help="busiest threads to break down, per arm")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--group", action="append", default=[], help="LABEL:REGEX over frames")
    parser.add_argument("--rate", type=float, default=None, help="py-spy sampling rate in Hz")
    parser.add_argument("--steps", type=float, default=None, help="iterations in the sampled window")
    parser.add_argument("--focus", default=None, help="REGEX: break down the stacks through this frame")
    parser.add_argument("--thread", default=None, help="REGEX: keep only matching threads")
    args = parser.parse_args()

    arms = []
    for spec in args.arm:
        label, path = spec.split("=", 1)
        threads, inclusive, groups_raw = load(path)
        if args.thread:
            keep = {t for t in threads if re.search(args.thread, t)}
            threads = Counter({t: n for t, n in threads.items() if t in keep})
            groups_raw = {t: v for t, v in groups_raw.items() if t in keep}
        arms.append((label, threads, inclusive, groups_raw))
    groups = [(g.split(":", 1)[0], re.compile(g.split(":", 1)[1])) for g in args.group]

    def unit(samples, total):
        if args.rate and args.steps:
            return f"{samples / args.rate * 1e3 / args.steps:.3f}"
        return f"{samples / max(total, 1):.1%}"

    unit_name = "ms/step" if args.rate and args.steps else "share of thread samples"
    for label, threads, inclusive, groups_raw in arms:
        print(f"## {label}: samples per thread")
        for thread, samples in threads.most_common():
            print(f"- {thread}: {samples} ({unit(samples, samples) if args.rate and args.steps else samples})")
        for thread, total in threads.most_common(args.threads):
            print(f"\n### {label} / {thread} ({total} samples), top functions by inclusive {unit_name}")
            print("| function | inclusive |\n|---|---:|")
            for frame, samples in inclusive[thread].most_common(args.top):
                print(f"| `{frame[:110]}` | {unit(samples, total)} |")
        print()

    if args.focus:
        focus = re.compile(args.focus)
        for label, threads, _, groups_raw in arms:
            callees, leaves = Counter(), Counter()
            for stacks in groups_raw.values():
                for frames, count in stacks:
                    index = next((i for i, frame in enumerate(frames) if focus.search(frame)), None)
                    if index is None:
                        continue
                    callees[frames[index + 1] if index + 1 < len(frames) else "(self)"] += count
                    leaves[frames[-1]] += count
            for title, counter in (("callees", callees), ("leaves", leaves)):
                print(f"### {label}: {title} under `{args.focus}` ({unit_name})")
                print("| frame | samples |\n|---|---:|")
                for frame, samples in counter.most_common(args.top):
                    print(f"| `{frame[:110]}` | {unit(samples, sum(threads.values()))} |")
                print()

    if groups:
        labels = [a[0] for a in arms]
        print(f"## groups ({unit_name}, busiest thread matching per arm summed over all threads)")
        header = "| group | " + " | ".join(labels) + (" | delta |" if len(arms) == 2 else " |")
        print(header)
        print("|---|" + "---:|" * (len(arms) + (1 if len(arms) == 2 else 0)))
        for name, pattern in groups:
            values = []
            for _, threads, _, groups_raw in arms:
                total = sum(threads.values())
                samples = sum(
                    count for stacks in groups_raw.values() for frames, count in stacks
                    if any(pattern.search(frame) for frame in frames)
                )
                values.append((samples, total))
            cells = [unit(s, t) for s, t in values]
            row = f"| {name} | " + " | ".join(cells)
            if len(arms) == 2 and args.rate and args.steps:
                row += f" | {(values[1][0] - values[0][0]) / args.rate * 1e3 / args.steps:+.3f}"
            print(row + " |")


if __name__ == "__main__":
    main()
