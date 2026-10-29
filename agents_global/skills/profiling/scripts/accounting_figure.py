# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib"]
# ///
"""Per-row delta bars from step_accounting.py CSVs: where one arm's step time goes relative to the other.

Each `--csv TITLE=PATH` (a two-arm step_accounting.py CSV, e.g. one per instrumentation) becomes a panel of
horizontal bars, one per row, showing the delta column (after minus before, ms per step). Bars that add time are
red, bars that save time blue (the validated diverging pair of the dataviz reference palette), with the value
printed at the bar end. `--fold PREFIX` (repeatable) merges all rows starting with PREFIX into one row (e.g.
"idle" or "exposed comm"), `--min-ms` drops rows whose delta is smaller in every panel, and rows keep one order
across panels. `--reference LABEL=MS` (repeatable) draws a dashed vertical line, e.g. the untraced step delta,
and `--total-label` names the summed row added at the bottom of each panel. `--panel-reference INDEX:LABEL=MS`
draws such a line on panel INDEX only (0-based, in `--csv` order), for panels whose arms differ in untraced step time.

Usage:
  uv run --script accounting_figure.py --out fig.png --csv "torch.profiler=a.csv" --csv "nsys=b.csv" \\
    --fold "idle" --fold "exposed comm" --min-ms 1 --reference "untraced step delta=45.8" \\
    --title "FP8 minus bf16, ms per step, 4L proxy, 4096 tokens per GPU"
"""

import argparse
import csv
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ADD, SAVE, INK, MUTED, SURFACE = "#e34948", "#2a78d6", "#1f1f1e", "#6b6b68", "#fcfcfb"


def load(path, folds):
    rows = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        if next(reader)[-1] != "delta":
            raise SystemExit(f"{path} has no delta column: pass a step_accounting.py CSV from a two-arm run")
        for row in reader:
            label, delta = row[0], float(row[-1])
            for prefix in folds:
                if label.startswith(prefix):
                    if prefix.startswith("idle"):
                        label = f"{prefix} (all causes)"
                    elif prefix.startswith("exposed comm"):
                        label = f"{prefix} (all collectives)"
                    else:
                        label = f"{prefix} (all rows)"
                    break
            rows[label] = rows.get(label, 0.0) + delta
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", action="append", required=True, help="TITLE=PATH of a two-arm step_accounting CSV")
    parser.add_argument("--out", required=True)
    parser.add_argument("--fold", action="append", default=[])
    parser.add_argument("--min-ms", type=float, default=0.5)
    parser.add_argument("--reference", action="append", default=[], help="LABEL=MS dashed line")
    parser.add_argument("--panel-reference", action="append", default=[],
                        help="INDEX:LABEL=MS dashed line on one panel (0-based)")
    parser.add_argument("--total-label", default="sum of rows (traced step delta)")
    parser.add_argument("--title", default="")
    args = parser.parse_args()

    panels = [(spec.split("=", 1)[0], load(spec.split("=", 1)[1], args.fold)) for spec in args.csv]
    labels = sorted({k for _, rows in panels for k in rows},
                    key=lambda k: -max(abs(rows.get(k, 0.0)) for _, rows in panels))
    labels = [k for k in labels if max(abs(rows.get(k, 0.0)) for _, rows in panels) >= args.min_ms]
    labels.append(args.total_label)

    fig, axes = plt.subplots(1, len(panels), figsize=(6.2 * len(panels), 0.42 * len(labels) + 1.6), sharey=True,
                             facecolor=SURFACE)
    axes = [axes] if len(panels) == 1 else list(axes)
    span = max(max(abs(v) for v in rows.values()) for _, rows in panels)
    span = max(span, max(abs(sum(rows.values())) for _, rows in panels))
    reference_texts = []
    panel_references = defaultdict(list)
    for spec in args.panel_reference:
        index, ref = spec.split(":", 1)
        panel_references[int(index)].append(ref)
    for index, (ax, (title, rows)) in enumerate(zip(axes, panels)):
        values = [rows.get(k, 0.0) for k in labels[:-1]] + [sum(rows.values())]
        ys = range(len(labels))
        colors = [ADD if v > 0 else SAVE for v in values]
        ax.barh(ys, values, color=colors, height=0.62, edgecolor=SURFACE, linewidth=2)
        for y, v in zip(ys, values):
            ax.text(v + (0.01 if v >= 0 else -0.01) * span * 2, y, f"{v:+.1f}", va="center",
                    ha="left" if v >= 0 else "right", fontsize=8.5, color=INK)
        ax.axvline(0, color=MUTED, linewidth=0.8)
        ax.axhline(len(labels) - 1.5, color=MUTED, linewidth=0.6, linestyle=":")
        for ref in args.reference + panel_references[index]:
            name, ms = ref.rsplit("=", 1)
            ax.axvline(float(ms), color=INK, linewidth=1.0, linestyle="--")
            reference_texts.append(
                ax.text(float(ms), len(labels) - 1.5, f" {name} {float(ms):+.1f}", fontsize=8, color=INK, va="bottom")
            )
        ax.set_xlim(-span * 1.35, span * 1.35)
        ax.set_title(title, fontsize=10, color=INK)
        ax.set_xlabel("ms per step (red adds time, blue saves time)", fontsize=9, color=MUTED)
        ax.grid(axis="x", color="#e6e5e1", linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_facecolor(SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=8.5)
    axes[0].set_yticks(range(len(labels)))
    axes[0].set_yticklabels([k[:70] for k in labels], fontsize=8.5, color=INK)
    axes[0].invert_yaxis()
    if args.title:
        fig.suptitle(args.title, fontsize=11, color=INK)
    fig.tight_layout()
    renderer = fig.canvas.get_renderer()
    for text in reference_texts:
        if text.get_window_extent(renderer).x1 > text.axes.get_window_extent(renderer).x1:
            text.set_horizontalalignment("right")
            text.set_text(f"{text.get_text().strip()} ")
    fig.savefig(args.out, dpi=160, facecolor=SURFACE)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
