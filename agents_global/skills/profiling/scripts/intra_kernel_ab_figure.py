# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib"]
# ///
"""PR-sized A/B figures from intra-kernel event tables: per-warp timelines and interval distributions.

Reads the tidy event tables of `intra_kernel_events.py` and uses the event-reference and interval syntax of
`intra_kernel_intervals.py` (`name`, `name.start`, `warp.end`, `@wN` / `@ROLE` selectors, `NAME=START:END`).

`timeline`: one panel per variant, stacked on a shared time axis in µs. Each panel shows one representative
CTA and iteration: the sample whose `--rep` interval is that variant's median, within the `--iteration` class
(`first` is iteration 0, `steady` the rest). Rows are the warps in `--rows` (`LABEL=wN` or `LABEL=ROLE`, top to
bottom). Each `--span LABEL=START:END:COLOR` draws a bar on every row whose warp has both events in that
iteration, and each `--mark LABEL=EVENT:COLOR` a tick. Time 0 is the `--anchor` event of that CTA and
iteration, so the panels are left-aligned at the same point of the kernel. Each panel's subtitle gives the
variant and its `--rep` length.

`dist`: one row per `--interval`, a box per variant (median line, p20-p80 box, p5-p95 whiskers), split by
`--iteration`. Lower is better for every interval.

Usage:
  uv run --script intra_kernel_ab_figure.py timeline np_cpasync.csv.gz np_tma.csv.gz --out tl.png \\
      --rep query=c_wait_q@w0:c_lse_done@w0 --anchor init_done@w0 --rows "WG0 warp 0=w0" --rows "producer=w8" \\
      --span "Q wait=c_wait_q:c_q_ready:#d55e00" --span "K wait=c_wait_k:c_k_ready:#e69f00" --title "..."
  uv run --script intra_kernel_ab_figure.py dist np_cpasync.csv.gz np_tma.csv.gz --out dist.png \\
      --interval q_wait=c_wait_q@w0:c_q_ready@w0 --interval k_wait=c_wait_k@w0:c_k_ready@w0 --title "..."
"""

import argparse
import os
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intra_kernel_intervals import interval_samples, parse_ref, read_events, resolve_warp  # noqa: E402

TEXT = "#333333"
GRID = "#dddddd"


def in_class(iteration: int, klass: str) -> bool:
    return iteration == 0 if klass == "first" else iteration > 0


def representative(events, roles, rep_spec: str, klass: str) -> dict:
    """{variant: (launch, cta, iteration, duration_ns)} at the median `rep_spec` duration."""
    _, samples = interval_samples(events, roles, rep_spec)
    chosen = {}
    for variant in events:
        mine = sorted((s for s in samples if s[0] == variant and in_class(s[4], klass)), key=lambda s: s[5])
        if not mine:
            raise SystemExit(f"{variant}: no {klass} samples of --rep {rep_spec}")
        _, launch, cta, _, iteration, duration, _ = mine[len(mine) // 2]
        chosen[variant] = (launch, cta, iteration, duration)
    return chosen


def event_time(warps, ref_text: str, roles, iteration: int, default_warp: int | None = None):
    ref, selector = parse_ref(ref_text)
    warp = resolve_warp(selector, roles) if selector else default_warp
    times = warps.get(warp, {}).get(ref, [])
    return times[iteration] if iteration < len(times) else None


def timeline(args) -> None:
    events, roles, _ = read_events(args.events)
    variants = list(events)
    chosen = representative(events, roles, args.rep, args.iteration)
    rows = [r.rsplit("=", 1) for r in args.rows]
    spans = [(label, *body.rsplit(":", 2)) for label, body in (s.split("=", 1) for s in args.span)]
    marks = [(label, *body.rsplit(":", 1)) for label, body in (m.split("=", 1) for m in args.mark)]
    fig, axes = plt.subplots(
        len(variants), 1, figsize=(args.width, 0.55 * len(rows) * len(variants) + 2.2), sharex=True
    )
    axes = [axes] if len(variants) == 1 else axes
    used = {}
    for ax, variant in zip(axes, variants):
        launch, cta, iteration, duration = chosen[variant]
        warps = events[variant][(launch, cta)]
        t0 = event_time(warps, args.anchor, roles[variant], iteration)
        if t0 is None:
            raise SystemExit(f"{variant}: anchor {args.anchor} missing in CTA {cta} iteration {iteration}")
        for y, (_, selector) in enumerate(rows):
            warp = resolve_warp(selector, roles[variant])
            for label, start, end, color in spans:
                t_start = event_time(warps, start, roles[variant], iteration, warp)
                t_end = event_time(warps, end, roles[variant], iteration, warp)
                if t_start is None or t_end is None:
                    continue
                left, width = (t_start - t0) / 1e3, max(t_end - t_start, 32) / 1e3
                used[label] = ax.barh(y, width, left=left, height=0.6, color=color, edgecolor="white", linewidth=1)
            for label, ref, color in marks:
                t = event_time(warps, ref, roles[variant], iteration, warp)
                if t is not None:
                    used[label] = ax.plot([(t - t0) / 1e3] * 2, [y - 0.38, y + 0.38], color=color, linewidth=2)[0]
        ax.set_yticks(range(len(rows)), [label for label, _ in rows], color=TEXT)
        ax.set_ylim(len(rows) - 0.5, -0.5)
        ax.set_title(
            f"{variant}: CTA {cta}, iteration {iteration}, {args.rep.split('=')[0]} {duration / 1e3:.2f} µs (median)",
            loc="left",
            fontsize=10,
            color=TEXT,
        )
        ax.grid(axis="x", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[-1].set_xlabel(args.xlabel or f"µs since {args.anchor} of the representative CTA and iteration", color=TEXT)
    if args.xlim:
        axes[-1].set_xlim(*args.xlim)
    ncol = min(len(used), 4)
    legend_height = 0.3 * -(-len(used) // ncol) / fig.get_figheight()
    fig.legend(used.values(), used.keys(), loc="lower center", ncol=ncol, frameon=False, fontsize=9)
    fig.suptitle(args.title, x=0.01, ha="left", fontsize=11, color=TEXT)
    fig.tight_layout(rect=(0, legend_height + 0.01, 1, 0.95))
    fig.savefig(args.out, dpi=args.dpi)
    print(f"wrote {args.out}", file=sys.stderr)


def dist(args) -> None:
    events, roles, _ = read_events(args.events)
    variants = list(events)
    results = [interval_samples(events, roles, spec) for spec in args.interval]
    fig, axes = plt.subplots(len(results), 1, figsize=(args.width, 0.45 * len(variants) * len(results) + 1.2))
    axes = [axes] if len(results) == 1 else axes
    colors = args.colors.split(",")
    for ax, (name, samples) in zip(axes, results):
        data, labels = [], []
        for variant in variants:
            values = [s[5] / 1e3 for s in samples if s[0] == variant and in_class(s[4], args.iteration)]
            data.append(values or [float("nan")])
            median = statistics.median(values) if values else float("nan")
            labels.append(f"{variant}  {median:.2f}")
        box = ax.boxplot(data, orientation="horizontal", whis=(5, 95), showfliers=False, widths=0.55, patch_artist=True)
        for patch, color in zip(box["boxes"], colors * len(variants)):
            patch.set(facecolor=color, alpha=0.85, edgecolor="white")
        for median_line in box["medians"]:
            median_line.set(color=TEXT, linewidth=1.5)
        ax.set_yticks(range(1, len(variants) + 1), labels, color=TEXT, fontsize=9)
        ax.invert_yaxis()
        ax.set_title(
            f"{name} ({args.iteration} iteration{'s' if args.iteration == 'steady' else ''}), µs, lower is better",
            loc="left",
            fontsize=10,
            color=TEXT,
        )
        ax.grid(axis="x", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle(args.title, x=0.01, ha="left", fontsize=11, color=TEXT)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(args.out, dpi=args.dpi)
    print(f"wrote {args.out}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("timeline", "dist"):
        p = sub.add_parser(name)
        p.add_argument("events", nargs="+")
        p.add_argument("--out", required=True)
        p.add_argument("--title", default="")
        p.add_argument("--iteration", choices=("first", "steady"), default="first")
        p.add_argument("--width", type=float, default=10)
        p.add_argument("--dpi", type=int, default=150)
    p_tl = sub.choices["timeline"]
    p_tl.add_argument("--rep", required=True, help="NAME=START:END whose median picks the representative CTA")
    p_tl.add_argument("--anchor", required=True, help="event reference at t = 0, e.g. init_done@w0")
    p_tl.add_argument(
        "--rows", action="append", required=True, help="LABEL=wN or LABEL=ROLE, repeatable, top to bottom"
    )
    p_tl.add_argument("--span", action="append", default=[], help="LABEL=START:END:COLOR, repeatable")
    p_tl.add_argument("--mark", action="append", default=[], help="LABEL=EVENT:COLOR, repeatable")
    p_tl.add_argument("--xlim", type=float, nargs=2)
    p_tl.add_argument("--xlabel")
    p_dist = sub.choices["dist"]
    p_dist.add_argument("--interval", action="append", required=True, help="NAME=START:END, repeatable")
    p_dist.add_argument("--colors", default="#0072b2,#d55e00,#009e73,#e69f00,#cc79a7,#56b4e9")
    args = parser.parse_args()
    {"timeline": timeline, "dist": dist}[args.command](args)


if __name__ == "__main__":
    main()
