"""Deduplicate the per-sync Python stacks written by sync_stacks/sitecustomize.py into call sites with counts per step.

Default steps: all but the first two (compile, warmup) and the last (it also covers post-loop work). A site is the
full stack plus the autograd node; it prints the innermost frame, the innermost project frames (outside
site-packages and the stdlib), and how many syncs each source saw. "stream"/"event"/"device" rows are the complete
count; "warn" (sync debug mode) duplicates stream syncs and misses event and device syncs.

Usage: python3 sync_stacks_report.py <syncs_rank0.jsonl> [--steps 3,4] [--depth 3] [--full]
"""

import argparse
import json
from collections import defaultdict

LIBRARY_MARKERS = ("/site-packages/", "/lib/python3")


def short(frame):
    path, line, func = frame
    for marker in ("/site-packages/", "/src/"):
        if marker in path:
            path = path.split(marker, 1)[1]
    return f"{path}:{line} {func}"


def project_frames(stack):
    return [f for f in stack if not any(m in f[0] for m in LIBRARY_MARKERS)]


def site_label(rec, depth=3):
    stack = rec["stack"]
    inner = short(stack[-1]) if stack else "<no Python frames>"
    callers = [c for c in (short(f) for f in project_frames(stack)[-depth:][::-1]) if c != inner]
    node = f"[{rec['node']}] " if rec.get("node") else ""
    return node + inner + "".join(f"  <- {c}" for c in callers)


def site_key(rec):
    return (rec.get("node"), tuple((f[0], f[1]) for f in rec["stack"]))


def load(path, steps=None):
    recs = [json.loads(line) for line in open(path)]
    all_steps = sorted({r["step"] for r in recs})
    steps = steps or all_steps[2:-1]
    return [r for r in recs if r["step"] in steps], steps


def main():
    p = argparse.ArgumentParser()
    p.add_argument("jsonl")
    p.add_argument("--steps", type=lambda s: [int(x) for x in s.split(",")])
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--full", action="store_true")
    args = p.parse_args()
    recs, steps = load(args.jsonl, args.steps)
    n = len(steps)
    sites = defaultdict(lambda: defaultdict(int))
    first = {}
    for r in recs:
        key = site_key(r)
        sites[key][r["source"]] += 1
        first.setdefault(key, r)
    by_source = defaultdict(int)
    for r in recs:
        by_source[r["source"]] += 1
    print(f"{args.jsonl}: steps {steps}, per step: " + ", ".join(f"{s} {c / n:.1f}" for s, c in sorted(by_source.items())))
    order = sorted(sites, key=lambda k: (-sum(v for s, v in sites[k].items() if s != "warn"), -sites[k].get("warn", 0)))
    for key in order:
        counts = ", ".join(f"{s} x{c / n:g}" for s, c in sorted(sites[key].items()))
        rec = first[key]
        print(f"  {counts:28} {rec['thread']:10} {site_label(rec, args.depth)}")
        if args.full:
            for f in rec["stack"]:
                print(f"      {short(f)}")


if __name__ == "__main__":
    main()
