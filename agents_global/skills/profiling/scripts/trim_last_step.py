# /// script
# requires-python = ">=3.10"
# ///
"""Write a copy of a torch.profiler chrome trace keeping metadata and events overlapping the last step.

Events that start before the window but overlap it are clipped to start at the window, so the copy doesn't
carry spans reaching back to the start of the run. The kept window starts at the last CPU-side `user_annotation`
event with the given name, or with `--annotation-span K` at the Kth-from-last one (torch also projects it onto the
GPU stream as a `gpu_user_annotation`, which this ignores). prime-rl wraps each micro-batch's forward in
`record_function("forward")`, so with K micro-batches per step pass `--annotation-span K` to keep the whole last
step. The name also matches `<name>#<n>`, so `--annotation ProfilerStep` keeps the last of torch.profiler's
per-step `ProfilerStep#<n>` ranges. Input and output may each be `.json` or `.json.gz` (gzipped when the output
name ends in `.gz`).

Usage: uv run --script trim_last_step.py <trace.json.gz> <out.json.gz> [--annotation forward] [--annotation-span 1]
"""

import argparse
import gzip
import json

from trace_events import is_marker, pick, read_trace

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("trace", help="torch.profiler chrome trace (.json or .json.gz)")
parser.add_argument("out", help="output path (.json.gz, or .json for plain JSON)")
parser.add_argument("--annotation", default="forward", help="CPU-side user_annotation that starts each step")
parser.add_argument("--annotation-span", type=int, default=1, help="keep from the Nth-from-last annotation on")
args = parser.parse_args()
src, dst, name = args.trace, args.out, args.annotation
trace = read_trace(src)
events = trace["traceEvents"]
markers = sorted(
    e["ts"] for e in events if e.get("ph") == "X" and e.get("cat") == "user_annotation" and is_marker(e["name"], name)
)
start = pick(markers, -args.annotation_span, f"CPU-side user_annotation `{name}` (or `{name}#<n>`)")
kept = []
for e in events:
    if e.get("ph") == "M":
        kept.append(e)
    elif "ts" in e and e["ts"] + e.get("dur", 0) >= start:
        if e["ts"] < start:
            e = dict(e, ts=start, dur=e["ts"] + e.get("dur", 0) - start) if "dur" in e else dict(e, ts=start)
        kept.append(e)
trace["traceEvents"] = kept
with (gzip.open if dst.endswith(".gz") else open)(dst, "wt") as f:
    json.dump(trace, f)
print(f"{dst}: kept {len(kept)} of {len(events)} events")
