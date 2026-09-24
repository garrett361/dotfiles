# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib"]
# ///
"""Before/after timeline figure from torch.profiler chrome traces, in the style of prime-rl PR #3638.

One panel per arm shows the main GPU stream's kernels in a window around an anchor kernel (the Nth launch
of that kernel inside the selected step), colored by category, with every arm aligned at the anchor. Without
`--anchor`, arms align at the step start. With two arms, a bottom panel shows the per-category change in
main-stream kernel time over the whole selected step (`--no-delta` omits it, e.g. when one rank's
kernel savings do not reach step time and the panel would mislead).

Steps start at the CPU-side `user_annotation` events named `--step-marker`; `--step-index` picks one (default
-1, the last) and the step runs until the next marker or the end of the trace. The main stream is the stream
with the most kernel time. Categories are `label:regex:color`, matched in order against kernel names;
unmatched kernels fall into "other".

`--anchor-annotation NAME` aligns at the Nth (`--anchor-index`) GPU-side `record_function` annotation with
exactly that name instead of a kernel, e.g. `FSDP::all_gather_copy_out (model.layers.2)`, which starts a
layer's compute; a window starting at 0 then left-aligns every arm. `--end-annotation NAME` marks the first
such annotation after the anchor as the end of a region: each panel gets a dashed line and the region's
length, and with two arms an arrow on the second panel labels the difference.

`--annotate-gaps MIN_MS` shades every interval of at least MIN_MS in the window where no stream of that GPU
runs a kernel, labeled with its length and, if one exists, the shortest CPU op or annotation spanning the
whole gap (what the host was inside). Gap details and all spanning CPU events are printed. A dashed line
marks the end of the step when it falls inside the window.

Usage:
  Preferred layout, left-aligned at the start of a region with its end marked (see reporting/figures.md):
  uv run --script timeline_figure.py --out fig.png --window -2 100 \\
    --anchor-annotation "FSDP::all_gather_copy_out (model.layers.2)" --end-annotation "<annotation ending it>" \\
    --trace "Before: ...=before/trace_0.json.gz" --trace "After: ...=after/trace_0.json.gz" --category ...
  Aligned at a kernel inside the region (reads worse: the axis runs negative):
  uv run --script timeline_figure.py --out fig.png --anchor main_kernel --anchor-index 2 \\
    --trace "Before: main (abc1234)=before/trace_0.json.gz" --trace "After: PR (def5678)=after/trace_0.json.gz" \\
    --category "torch.cat:CatArrayBatchedCopy:#d55e00" --category "GEMM:^nvjet|cutlass(?!.*rmsnorm):#0072b2" \\
    --window -65 25 --title "Model, scale, shared settings"
  Whole-step stall view, aligned at the start of the third traced step:
  uv run --script timeline_figure.py --out stall.png --step-index 2 --window -200 30000 --annotate-gaps 1000 \\
    --trace "Before: ...=before/trace_0.json.gz" --trace "After: ...=after/trace_0.json.gz" --title "..."
"""

import argparse
import gzip
import json
import re
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

OTHER = ("other", None, "#999999")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--trace", action="append", required=True, help="LABEL=PATH, in panel order")
    parser.add_argument("--anchor", default=None, help="kernel name to align arms on (default: step start)")
    parser.add_argument("--anchor-index", type=int, default=0, help="which occurrence of the anchor in the step")
    parser.add_argument("--anchor-annotation", default=None, help="GPU annotation name to align arms on")
    parser.add_argument("--end-annotation", default=None, help="GPU annotation name that ends the marked region")
    parser.add_argument("--region-label", default="region", help="wording for the marked region")
    parser.add_argument("--step-index", type=int, default=-1, help="which step-marker event starts the step")
    parser.add_argument("--annotate-gaps", type=float, default=None, metavar="MIN_MS", help="mark GPU idle gaps")
    parser.add_argument("--window", type=float, nargs=2, default=(-50.0, 50.0), metavar=("LO_MS", "HI_MS"))
    parser.add_argument("--category", action="append", default=[], help="label:regex:color, matched in order")
    parser.add_argument("--step-marker", default="forward")
    parser.add_argument("--title", default="")
    parser.add_argument("--anchor-label", default=None, help="x-axis wording for the anchor")
    parser.add_argument("--no-delta", action="store_true", help="omit the per-category delta panel")
    return parser.parse_args()


def parse_categories(specs):
    categories = []
    for spec in specs:
        label, rest = spec.split(":", 1)
        pattern, color = rest.rsplit(":", 1)
        categories.append((label, re.compile(pattern), color))
    return categories + [OTHER]


def categorize(name, categories):
    return next((label, color) for label, pattern, color in categories if pattern is None or pattern.search(name))


def load_step(path, step_marker, step_index):
    events = [e for e in json.load(gzip.open(path))["traceEvents"] if e.get("ph") == "X"]
    starts = sorted(e["ts"] for e in events if e.get("cat") == "user_annotation" and e.get("name") == step_marker)
    start = starts[step_index]
    end = next((ts for ts in starts if ts > start), float("inf"))
    kernels = [e for e in events if e.get("cat") == "kernel" and start <= e["ts"] < end]
    per_stream = defaultdict(float)
    for e in kernels:
        per_stream[(e["pid"], e["tid"])] += e["dur"]
    main = max(per_stream, key=per_stream.get)
    stream = sorted((e for e in kernels if (e["pid"], e["tid"]) == main), key=lambda e: e["ts"])
    device = sorted((e for e in kernels if e["pid"] == main[0]), key=lambda e: e["ts"])
    host = [e for e in events if e.get("cat") in ("cpu_op", "user_annotation")]
    gpu_annotations = sorted(
        (e for e in events if e.get("cat") == "gpu_user_annotation" and start <= e["ts"] < end), key=lambda e: e["ts"]
    )
    return {"start": start, "end": end, "stream": stream, "device": device, "host": host, "annotations": gpu_annotations}


def idle_gaps(kernels, lo, hi, min_us):
    gaps, busy_until = [], None
    for e in kernels:
        if e["ts"] + e["dur"] < lo or e["ts"] > hi:
            continue
        if busy_until is not None and e["ts"] - busy_until >= min_us:
            gaps.append((busy_until, e["ts"]))
        busy_until = max(busy_until or 0.0, e["ts"] + e["dur"])
    return gaps


def format_us(us):
    return f"{us / 1e6:.2f} s" if us >= 1e6 else f"{us / 1e3:.1f} ms"


def annotate_gaps(ax, step, anchor_ts, lo, hi, min_ms, label):
    gaps = idle_gaps(step["device"], anchor_ts + lo * 1e3, anchor_ts + hi * 1e3, min_ms * 1e3)
    print(f"{label}: {len(gaps)} GPU idle gaps >= {min_ms:g} ms")
    for gap_start, gap_end in gaps:
        spanning = sorted(
            (e for e in step["host"] if e["ts"] <= gap_start and e["ts"] + e["dur"] >= gap_end), key=lambda e: e["dur"]
        )
        print(f"  {format_us(gap_end - gap_start)} at {(gap_start - anchor_ts) / 1e3:.1f} ms")
        for e in spanning:
            print(f"    spanned by {e['cat']} {e['name']} ({format_us(e['dur'])})")
        x0, x1 = (gap_start - anchor_ts) / 1e3, (gap_end - anchor_ts) / 1e3
        ax.axvspan(x0, x1, color="#cc0000", alpha=0.12, linewidth=0)
        ax.annotate("", xy=(x0, 0.85), xytext=(x1, 0.85), arrowprops=dict(arrowstyle="<->", color="#cc0000"))
        text = f"GPU idle {format_us(gap_end - gap_start)}"
        if spanning:
            text += f"\nhost inside {spanning[0]['name']}"
        ax.text((x0 + x1) / 2, 0.45, text, ha="center", va="center", fontsize=10, color="#cc0000", clip_on=True)


def main():
    args = parse_args()
    categories = parse_categories(args.category)
    arms = []
    for spec in args.trace:
        label, path = spec.split("=", 1)
        arms.append((label, load_step(path, args.step_marker, args.step_index)))

    show_delta = len(arms) == 2 and not args.no_delta
    heights = [1] * len(arms) + ([1.4] if show_delta else [])
    fig = plt.figure(figsize=(14, 2.8 * len(heights) + 0.6))
    grid = fig.add_gridspec(len(heights), 1, height_ratios=heights, hspace=0.6)
    lo, hi = args.window
    totals, region_ends, axes = [], [], []
    for row, (label, step) in enumerate(arms):
        ax = fig.add_subplot(grid[row])
        stream = step["stream"]
        if args.anchor_annotation:
            anchor_ts = [e for e in step["annotations"] if e["name"] == args.anchor_annotation][args.anchor_index]["ts"]
        elif args.anchor:
            anchor_ts = [e for e in stream if e["name"] == args.anchor][args.anchor_index]["ts"]
        else:
            anchor_ts = step["start"]
        for e in stream:
            t0 = (e["ts"] - anchor_ts) / 1e3
            if lo <= t0 <= hi:
                color = categorize(e["name"], categories)[1]
                ax.broken_barh([(t0, e["dur"] / 1e3)], (0, 1), facecolors=color, edgecolor="white", linewidth=0.3)
        ax.set_xlim(lo, hi)
        ax.set_yticks([])
        ax.axvline(0, color="gray", linewidth=0.8)
        ax.grid(axis="x", alpha=0.3)
        ax.set_title(label, loc="left", fontsize=11)
        if args.annotate_gaps is not None:
            annotate_gaps(ax, step, anchor_ts, lo, hi, args.annotate_gaps, label)
        if args.end_annotation:
            end_ts = next(e["ts"] for e in step["annotations"] if e["name"] == args.end_annotation and e["ts"] > anchor_ts)
            region_end = (end_ts - anchor_ts) / 1e3
            region_ends.append(region_end)
            ax.axvline(region_end, color="black", linestyle="--", linewidth=1)
            ax.text(region_end, 1.04, f"{args.region_label}: {region_end:.1f} ms", ha="center", va="bottom", fontsize=10,
                    transform=ax.get_xaxis_transform())
            print(f"{label}: {args.region_label} {region_end:.1f} ms")
        axes.append(ax)
        step_end = (step["end"] - anchor_ts) / 1e3
        if lo < step_end < hi:
            ax.axvline(step_end, color="black", linestyle="--", linewidth=1)
            ax.text(step_end, 0.5, " step end", ha="left", va="center", fontsize=10)
        per_category = defaultdict(float)
        for e in stream:
            per_category[categorize(e["name"], categories)[0]] += e["dur"] / 1e3
        totals.append(per_category)
        if row == len(arms) - 1:
            if args.anchor_annotation:
                default_anchor = args.anchor_annotation
            elif args.anchor:
                default_anchor = f"launch {args.anchor_index} of {args.anchor}"
            else:
                default_anchor = "step start"
            anchor_label = args.anchor_label or default_anchor
            step_label = "last step" if args.step_index == -1 else f"step index {args.step_index}"
            ax.set_xlabel(f"ms relative to {anchor_label} ({step_label}, main GPU stream)")

    if len(region_ends) == 2:
        (before_end, after_end), ax = region_ends, axes[1]
        ax.axvline(before_end, color="#cc0000", linestyle=":", linewidth=1)
        ax.annotate("", xy=(after_end, 0.5), xytext=(before_end, 0.5), arrowprops=dict(arrowstyle="<->", color="#cc0000"))
        ax.text((before_end + after_end) / 2, 0.62, f"{after_end - before_end:+.1f} ms", ha="center", va="bottom",
                fontsize=11, color="#cc0000", fontweight="bold")

    labels = [label for label, _, _ in categories]
    if show_delta:
        ax = fig.add_subplot(grid[len(arms)])
        before, after = totals
        deltas = [after.get(k, 0.0) - before.get(k, 0.0) for k in labels]
        ax.barh(labels, deltas, color=[color for _, _, color in categories])
        span = max(abs(d) for d in deltas) or 1.0
        for y, d in enumerate(deltas):
            offset = 0.02 * span if d >= 0 else -0.02 * span
            ax.text(d + offset, y, f"{d:+.1f} ms", va="center", ha="left" if d >= 0 else "right", fontsize=9)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.invert_yaxis()
        ax.set_xlim(-1.35 * span, 1.35 * span)
        total_before, total_after = sum(before.values()), sum(after.values())
        ax.set_title(
            f"Main-stream kernel time per step, {arms[1][0].split(':')[0]} minus {arms[0][0].split(':')[0]}: "
            f"{total_after - total_before:+.1f} ms ({total_before:.0f} -> {total_after:.0f} ms)",
            loc="left",
            fontsize=11,
        )
        for label, d in zip(labels, deltas):
            print(f"{label:24s} {before.get(label, 0.0):9.1f} -> {after.get(label, 0.0):9.1f} ms  ({d:+.1f})")

    handles = [Patch(color=color, label=label) for label, _, color in categories]
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False, bbox_to_anchor=(0.5, 0.965))
    if args.title:
        fig.suptitle(args.title, fontsize=13, y=0.995)
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
