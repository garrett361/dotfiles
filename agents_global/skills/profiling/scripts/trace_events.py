# /// script
# requires-python = ">=3.10"
# ///
"""Shared loading helpers for torch.profiler chrome traces, plus a CLI that lists host ranges in a window.

Library (imported by comm_waits.py and timeline_figure.py):
- `load_trace(path)` returns a `Trace` with complete events split by category, kernels joined to their launch
  (`cuda_runtime`/`cuda_driver` event with the same `args["correlation"]`), and per-thread host stacks.
- `Trace.enclosing(launch, pattern)` returns the innermost host event (cpu_op or user_annotation) on the launch's
  thread that spans the launch and whose name matches `pattern`.
- `Trace.window(marker, index)` returns the [start, end) of the `index`th CPU-side `user_annotation` named
  `marker`, from its start to its end (`span="event"`) or to the next marker of that name (`span="next"`).
  A marker also matches `<marker>#<n>`, so `ProfilerStep` selects torch.profiler's per-step `ProfilerStep#<n>`.
- `read_trace(path)` loads a `.json` or `.json.gz` chrome trace; `is_marker(name, marker)` is the marker match
  above; `pick(events, index, what)` indexes a list or exits with a message naming what was missing.
- `Trace.main_stream(kernels, exclude)` is the (pid, tid) with the most kernel time among `kernels`, ignoring
  kernels matching `exclude` (pass the NCCL pattern when communication can outweigh compute).

CLI: print every host range on the busiest host thread inside a window, indented by nesting, to learn a
trace's annotation structure before writing category or label regexes. `--list-annotations REGEX` instead
prints every distinct CPU-side (`user_annotation`) and GPU-side (`gpu_user_annotation`) annotation name matching
the regex, with its count, which finds anchor names (e.g. for `timeline_figure.py --anchor-annotation`) that do
not run on the busiest thread, such as backward hooks on autograd's thread. `--include-python` also prints the
Python frames (from a `with_stack=True` profile) and CUDA runtime/driver calls, to attribute host time inside an
op down to the Python function or the launch call.

Usage:
  uv run --script trace_events.py <trace.json.gz> --from-annotation "FSDP::pre_backward (model.layers.12)" \\
    [--from-index -1] [--to-annotation "FSDP::post_backward_reduce (model.layers.12) [pg=16]"] \\
    [--name-filter REGEX] [--min-us 0] [--max-depth 6] [--include-python]
  uv run --script trace_events.py <trace.json.gz> --list-annotations "layers\\.4\\b"
"""

import argparse
import bisect
import gzip
import json
import re
import sys
from collections import defaultdict

HOST_CATEGORIES = ("cpu_op", "user_annotation")
LAUNCH_CATEGORIES = ("cuda_runtime", "cuda_driver")
PYTHON_CATEGORIES = ("python_function", *LAUNCH_CATEGORIES)


class Trace:
    def __init__(self, events, extra_host_categories=()):
        complete = [e for e in events if e.get("ph") == "X"]
        self.kernels = sorted((e for e in complete if e.get("cat") == "kernel"), key=lambda e: e["ts"])
        self.host = [e for e in complete if e.get("cat") in HOST_CATEGORIES + tuple(extra_host_categories)]
        self.gpu_annotations = sorted(
            (e for e in complete if e.get("cat") == "gpu_user_annotation"), key=lambda e: e["ts"]
        )
        launches = {}
        for e in complete:
            if e.get("cat") in LAUNCH_CATEGORIES and "correlation" in e.get("args", {}):
                launches[e["args"]["correlation"]] = e
        for kernel in self.kernels:
            kernel["launch"] = launches.get(kernel.get("args", {}).get("correlation"))
        self._by_thread = defaultdict(list)
        for e in self.host:
            self._by_thread[(e["pid"], e["tid"])].append(e)
        self._starts = {}
        for key, thread_events in self._by_thread.items():
            thread_events.sort(key=lambda e: (e["ts"], -e.get("dur", 0)))
            self._starts[key] = [e["ts"] for e in thread_events]

    def annotations(self, name_pattern):
        """CPU-side user annotations whose name matches the pattern, by start time."""
        pattern = re.compile(name_pattern)
        return sorted(
            (e for e in self.host if e.get("cat") == "user_annotation" and pattern.search(e["name"])),
            key=lambda e: e["ts"],
        )

    def window(self, marker, index=-1, span="event"):
        starts = [e for e in self.host if e.get("cat") == "user_annotation" and is_marker(e["name"], marker)]
        starts.sort(key=lambda e: e["ts"])
        event = pick(starts, index, f"CPU-side user_annotation `{marker}`")
        if span == "event":
            return event["ts"], event["ts"] + event["dur"]
        return event["ts"], next((e["ts"] for e in starts if e["ts"] > event["ts"]), float("inf"))

    def enclosing(self, launch, pattern):
        """Innermost host event on the launch's thread that spans it and matches the compiled pattern."""
        if launch is None:
            return None
        key = (launch["pid"], launch["tid"])
        thread_events = self._by_thread.get(key, [])
        upper = bisect.bisect_right(self._starts.get(key, []), launch["ts"])
        for e in reversed(thread_events[:upper]):
            if e["ts"] + e.get("dur", 0) >= launch["ts"] and pattern.search(e["name"]):
                return e
        return None

    def busiest_thread(self, lo, hi):
        busy = defaultdict(float)
        for key, thread_events in self._by_thread.items():
            for e in thread_events:
                if lo <= e["ts"] < hi:
                    busy[key] += e.get("dur", 0)
        return max(busy, key=busy.get)

    def thread_events(self, key):
        return self._by_thread[key]

    @staticmethod
    def main_stream(kernels, exclude=None):
        """Stream with the most kernel time, not counting kernels whose name matches `exclude` (e.g. NCCL)."""
        pattern = re.compile(exclude) if exclude else None
        per_stream = defaultdict(float)
        for e in kernels:
            if pattern is None or not pattern.search(e["name"]):
                per_stream[(e["pid"], e["tid"])] += e["dur"]
        return max(per_stream, key=per_stream.get)


def read_trace(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as f:
        return json.load(f)


def is_marker(name, marker):
    return name == marker or re.fullmatch(re.escape(marker) + r"#\d+", name) is not None


def pick(events, index, what):
    if not -len(events) <= index < len(events):
        sys.exit(
            f"index {index} is out of range: the trace has {len(events)} {what}"
            " (list annotation names with `trace_events.py <trace> --list-annotations ''`)"
        )
    return events[index]


def load_trace(path, extra_host_categories=()):
    return Trace(read_trace(path)["traceEvents"], extra_host_categories)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("trace")
    parser.add_argument("--from-annotation", help="CPU user_annotation name (or name#<n>) opening the window")
    parser.add_argument(
        "--list-annotations", metavar="REGEX", help="list distinct CPU and GPU annotation names matching REGEX, then exit"
    )
    parser.add_argument("--from-index", type=int, default=-1, help="which occurrence opens the window")
    parser.add_argument("--to-annotation", default=None, help="first later annotation with this name closes it")
    parser.add_argument("--name-filter", default=None, help="only print ranges whose name matches this regex")
    parser.add_argument("--min-us", type=float, default=0.0, help="only print ranges at least this long")
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument(
        "--include-python", action="store_true", help="also print Python frames and CUDA runtime/driver calls"
    )
    args = parser.parse_args()

    trace = load_trace(args.trace, PYTHON_CATEGORIES if args.include_python else ())
    if args.list_annotations is not None:
        pattern = re.compile(args.list_annotations)
        for side, events in (("cpu", trace.annotations("")), ("gpu", trace.gpu_annotations)):
            counts = defaultdict(int)
            for e in events:
                if pattern.search(e["name"]):
                    counts[e["name"]] += 1
            for name, count in sorted(counts.items()):
                print(f"{side} {count:5d}  {name}")
        return
    if args.from_annotation is None:
        parser.error("--from-annotation is required unless --list-annotations is given")
    opener = pick(
        [e for e in trace.annotations("") if is_marker(e["name"], args.from_annotation)],
        args.from_index,
        f"CPU-side user_annotation `{args.from_annotation}`",
    )
    lo = opener["ts"]
    hi = opener["ts"] + opener["dur"]
    if args.to_annotation:
        closers = [e for e in trace.annotations("") if is_marker(e["name"], args.to_annotation) and e["ts"] > lo]
        closer = pick(closers, 0, f"CPU-side user_annotation `{args.to_annotation}` after the opening one")
        hi = closer["ts"] + closer["dur"]
    key = trace.busiest_thread(lo, hi)
    name_filter = re.compile(args.name_filter) if args.name_filter else None
    stack = []
    for e in trace.thread_events(key):
        if not lo <= e["ts"] < hi:
            continue
        while stack and stack[-1] <= e["ts"]:
            stack.pop()
        depth = len(stack)
        stack.append(e["ts"] + e.get("dur", 0))
        if depth > args.max_depth or e.get("dur", 0) < args.min_us:
            continue
        if name_filter and not name_filter.search(e["name"]):
            continue
        print(f"{(e['ts'] - lo) / 1e3:10.3f} ms {e.get('dur', 0) / 1e3:9.3f} ms {'  ' * depth}{e['name'][:120]}")


if __name__ == "__main__":
    main()
