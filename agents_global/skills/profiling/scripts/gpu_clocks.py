# /// script
# requires-python = ">=3.10"
# ///
"""Summarize `nvidia-smi --query-gpu=... --format=csv -lms N` logs: SM clock, power and throttle reasons while busy.

Answers "did both arms run at the same clocks?" for a timing run. Each input is one CSV log, optionally labeled
`LABEL=path`. Recognized columns (by header prefix): `index`, `clocks.current.sm` / `clocks.sm`, `power.draw`,
`temperature.gpu`, `clocks_event_reasons.active`; others are ignored. Only busy samples (power above `--busy-watts`,
default 200 W; idle H200s draw about 75 W) enter the statistics, so the idle head and tail of a log do not dilute
them. `power.draw` is averaged over about a second, so short bursts (under ~0.5 s of GPU work between idle gaps) never
reach 200 W: lower `--busy-watts` (e.g. 100) for those. Per log (and per GPU with `--per-gpu`) it prints sample counts, busy GPU-seconds (busy samples times the median
sampling interval), the SM clock median, p20 and p80, the median power, the maximum temperature, and the share of
busy samples with each active throttle reason bit (e.g. 0x4 SW power cap).

Usage: uv run --script gpu_clocks.py [LABEL=]log.csv [...] [--busy-watts 200] [--per-gpu] [--decimals 0]
"""

import argparse
import csv
import statistics
from datetime import datetime

REASONS = {
    0x1: "idle",
    0x2: "app clocks",
    0x4: "SW power cap",
    0x8: "HW slowdown",
    0x10: "sync boost",
    0x20: "SW thermal",
    0x40: "HW thermal",
    0x80: "HW power brake",
    0x100: "display clocks",
}


def column(header, *prefixes):
    for i, name in enumerate(header):
        if any(name.strip().startswith(p) for p in prefixes):
            return i
    return None


def number(text):
    return float(text.strip().split()[0])


def quantile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def read_log(path):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], [r for r in rows[1:] if r and not r[0].startswith("timestamp")]
    cols = {
        "time": column(header, "timestamp"),
        "gpu": column(header, "index"),
        "sm": column(header, "clocks.current.sm", "clocks.sm"),
        "power": column(header, "power.draw"),
        "temp": column(header, "temperature.gpu"),
        "reasons": column(header, "clocks_event_reasons.active", "clocks_throttle_reasons.active"),
    }
    samples = []
    for r in body:
        try:
            samples.append(
                {
                    "time": datetime.strptime(r[cols["time"]].strip(), "%Y/%m/%d %H:%M:%S.%f")
                    if cols["time"] is not None
                    else None,
                    "gpu": r[cols["gpu"]].strip() if cols["gpu"] is not None else "all",
                    "sm": number(r[cols["sm"]]),
                    "power": number(r[cols["power"]]),
                    "temp": number(r[cols["temp"]]) if cols["temp"] is not None else None,
                    "reasons": int(r[cols["reasons"]].strip(), 16) if cols["reasons"] is not None else 0,
                }
            )
        except (ValueError, IndexError):
            continue
    return samples


def interval_s(samples):
    gaps = []
    for gpu in {s["gpu"] for s in samples}:
        times = [s["time"] for s in samples if s["gpu"] == gpu and s["time"] is not None]
        gaps += [(b - a).total_seconds() for a, b in zip(times, times[1:]) if b > a]
    return statistics.median(gaps) if gaps else 0.0


def summarize(label, samples, busy_watts, decimals):
    busy = [s for s in samples if s["power"] > busy_watts]
    row = [label, str(len(samples)), str(len(busy))]
    if not busy:
        return row + [f"{len(busy) * interval_s(samples):.1f}"] + ["-"] * 6
    sm = [s["sm"] for s in busy]
    temps = [s["temp"] for s in busy if s["temp"] is not None]
    bits = {}
    for s in busy:
        for bit, name in REASONS.items():
            if s["reasons"] & bit:
                bits[name] = bits.get(name, 0) + 1
    reasons = ", ".join(f"{n} {100 * c / len(busy):.0f}%" for n, c in sorted(bits.items(), key=lambda kv: -kv[1]))
    fmt = f"{{:.{decimals}f}}"
    return row + [
        f"{len(busy) * interval_s(samples):.1f}",
        fmt.format(statistics.median(sm)),
        fmt.format(quantile(sm, 0.2)),
        fmt.format(quantile(sm, 0.8)),
        fmt.format(statistics.median(s["power"] for s in busy)),
        fmt.format(max(temps)) if temps else "-",
        reasons or "none",
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logs", nargs="+", help="[LABEL=]path to an nvidia-smi CSV log")
    parser.add_argument("--busy-watts", type=float, default=200.0, help="power above which a sample counts as busy")
    parser.add_argument("--per-gpu", action="store_true", help="one row per GPU index instead of one per log")
    parser.add_argument("--decimals", type=int, default=0)
    args = parser.parse_args()

    print(
        "| log | samples | busy samples | busy GPU-s | SM MHz median | p20 | p80 | power W median | max temp C "
        "| throttle reasons (share of busy) |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for spec in args.logs:
        label, _, path = spec.partition("=") if "=" in spec else (spec, "", spec)
        samples = read_log(path)
        if args.per_gpu:
            for gpu in sorted({s["gpu"] for s in samples}, key=lambda g: (len(g), g)):
                subset = [s for s in samples if s["gpu"] == gpu]
                print("| " + " | ".join(summarize(f"{label} GPU {gpu}", subset, args.busy_watts, args.decimals)) + " |")
        else:
            print("| " + " | ".join(summarize(label, samples, args.busy_watts, args.decimals)) + " |")


if __name__ == "__main__":
    main()
