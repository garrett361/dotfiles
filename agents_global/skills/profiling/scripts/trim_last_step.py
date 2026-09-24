"""Write a gzipped copy of a torch.profiler chrome trace keeping metadata and events overlapping the last step.

Events that start before the window but overlap it are clipped to start at the window, so the copy doesn't
carry spans reaching back to the start of the run. The last step starts at the last CPU-side `user_annotation`
event with the given name (prime-rl SFT wraps each
step's forward in `record_function("forward")`; torch also projects it onto the GPU stream as a
`gpu_user_annotation`, which this ignores).

Usage: python3 trim_last_step.py <trace.json.gz> <out.json.gz> [--annotation forward]
"""

import argparse
import gzip
import json

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("trace", help="torch.profiler chrome trace (.json.gz)")
parser.add_argument("out", help="output path (.json.gz)")
parser.add_argument("--annotation", default="forward", help="CPU-side user_annotation that starts each step")
args = parser.parse_args()
src, dst, name = args.trace, args.out, args.annotation
trace = json.load(gzip.open(src))
events = trace["traceEvents"]
start = max(e["ts"] for e in events if e.get("ph") == "X" and e.get("cat") == "user_annotation" and e.get("name") == name)
kept = []
for e in events:
    if e.get("ph") == "M":
        kept.append(e)
    elif "ts" in e and e["ts"] + e.get("dur", 0) >= start:
        if e["ts"] < start:
            e = dict(e, ts=start, dur=e["ts"] + e.get("dur", 0) - start) if "dur" in e else dict(e, ts=start)
        kept.append(e)
trace["traceEvents"] = kept
with gzip.open(dst, "wt") as f:
    json.dump(trace, f)
print(f"{dst}: kept {len(kept)} of {len(events)} events")
