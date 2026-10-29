# /// script
# requires-python = ">=3.10"
# ///
"""Exposed-communication decomposition of a communication-plus-GEMM launch, comparable across implementations.

End-to-end time alone cannot tell "hid more communication" from "gave up compute elsewhere". This script splits each
implementation's time over the dense GEMM into the SMs it took from the GEMM, the time its GEMM programs measurably
waited for data, and a residual, and reports how much of the communication's standalone time it hid. Method,
definitions and pitfalls: `tools/exposed-comm.md`.

Inputs: one or more `bench_ops.py --csv` files (columns case, label, median_ms; rows whose label ends in " (B)" are
the second pass of an ABBA run and are averaged with the first pass), `--case` (substring selecting one case), and per
case:
  --comm LABEL         the communication kernel alone (C)
  --gemm-full LABEL    the GEMM alone on already-communicated data, all SMs (G_full)
  --arm 'NAME|impl=LABEL[|gemm_cap=LABEL][|comm=LABEL][|events=GLOB][|recorded=LABEL][|direct]'
       one implementation: impl is its timed label (T); gemm_cap the GEMM alone at the program cap the implementation
       leaves to the GEMM (G_P, default G_full; time it with the implementation's own binary, flags preset ready and
       no communication); comm a per-arm communication-alone label (default --comm); events the tidy intra-kernel
       tables (`intra_kernel_events.py` format, one file per rank) of an instrumented run of it; recorded the timed
       label of that instrumented run (prints recorded / unrecorded time, flagged above 1%); direct marks an
       implementation whose communication runs as its own kernel on the stream (separate launches): with events
       (both kernels' programs in one launch table) its (b) is measured, without them it is assumed to be C.

Definitions (all times are medians in ms; E, (a), (b), (c) add up to T - G_full):
  E = T - G_full                 exposed communication
  (a) = G_P - G_full             SM-share cost: the GEMM slowed by the programs or SMs the communication took
  (b) direct exposure            critical-path wait from the events (below), or C for a `direct` arm without events
  (c) = E - (a) - (b)            residual: contention (memory, L2, NoC), launch gaps, clocks
  H = 1 - E / C                  share of the communication's standalone time absent from wall time
  H_P = 1 - (T - G_P) / C        the same given the SMs it took
  H_max = min(1, G_full / C)     perfect-overlap bound: T >= max(C, G_full), so a launch whose communication alone
                                 outlasts the dense GEMM cannot hide all of it
  H_<ref> = 1 - E / E_ref        with `--ref-arm NAME`: share of the reference arm's exposed time removed. Use the
                                 separate-launch arm as the reference when C alone is not the communication's cost in
                                 sequence (a lockstep standalone run can be slower than its in-sequence share)
Direct exposure from events: per launch and GEMM program, its start delay after the launch's first program (any
role; for separate launches this covers the copy kernel and the launch gap) plus the summed wait from each tile's
start event to its ready event (`--tile-start`, `--tile-ready`), which includes self-help copies done inside the wait
(`--help` ranges); spin is wait minus self-help. (b) is that of the GEMM program that ends last (its waits sit on the
kernel's critical path: with balanced static tile assignment the kernel end moves by that program's waits), median
over launches; the mean over GEMM programs is reported beside it. With one event table per rank, (b) is taken from the
rank with the longest median traced span (the timing reports the slowest rank) and the range over ranks is shown.

Clocks: `--clock-prefix P` reads one nvidia-smi log per label at "P__<label slug>.csv" (the slug replaces every run of
non-alphanumerics with "_"; ABBA second passes at their own slug, merged) and reports the busy median SM MHz per
label. The decomposition is only valid when every label ran at the same SM clock: a label whose busy median differs
from the G_full label's by more than `--clock-tol-mhz` is flagged and the run should be repeated below the power cap
(`exposed_comm_controls.py` shows how). Under a power cap a separate copy kernel lowers average power, so the GEMM
after it runs at a higher clock than G_full, and that clock credit shows up as a negative (c) and a positive H for a
strictly serial arm (measured: H = +25% for copy-then-GEMM). The clock-normalized columns (t * f_label / f_ref; for
a `direct` arm only its GEMM part, T_norm = C + (T - C) * f_T / f_ref) are printed for reference only: in the same
control they overcorrected to H = -28%, because a capped GEMM does not speed up as 1/f.

Usage:
  uv run --script exposed_comm.py run.csv --case "FC13 FPROP" --comm "gather_rows only" \\
      --gemm-full "gemm (dense roofline)" --arm 'separate|impl=gather_rows+gemm|direct' --ref-arm separate \\
      --arm 'fused|impl=fused default G12 SUB32|gemm_cap=gemm (num_sms 120)|events=ev/flash_fprop_rank*.csv.gz' \\
      [--clock-prefix clocks/run] [--busy-watts 200] [--clock-tol-mhz 30] [--decimals 3]

Known-answer controls for this script: `exposed_comm_controls.py`.
"""

import argparse
import csv
import glob
import gzip
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gpu_clocks import read_log  # noqa: E402


def read_times(paths, case):
    """{label: median ms} for the case, ABBA second passes averaged into their first-pass label."""
    passes = defaultdict(list)
    names = set()
    for path in paths:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if case in row["case"]:
                    names.add(row["case"])
                    label = row["label"].removesuffix(" (B)")
                    passes[label].append(float(row["median_ms"]))
    if len(names) != 1:
        raise SystemExit(f"--case {case!r} matched {len(names)} cases: {sorted(names)}")
    return names.pop(), {label: statistics.mean(v) for label, v in passes.items()}, passes


def slug(label):
    return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")


def clock_mhz(prefix, label, busy_watts):
    """Busy median SM clock over the label's (and its ABBA second pass's) logs, or None."""
    samples = []
    for name in (label, f"{label} (B)"):
        path = f"{prefix}__{slug(name)}.csv"
        if os.path.exists(path):
            samples += [s for s in read_log(path) if s["power"] > busy_watts]
    return statistics.median(s["sm"] for s in samples) if samples else None


def read_events(path):
    """{launch: {program: {"role", "end", "events": [(event, phase, t_ns)]}}} from one tidy table."""
    opener = gzip.open if path.endswith(".gz") else open
    launches = defaultdict(lambda: defaultdict(lambda: {"role": "", "end": None, "start": None, "events": []}))
    with opener(path, "rt", newline="") as f:
        for row in csv.DictReader(f):
            prog = launches[int(row["launch"])][int(row["cta"])]
            prog["role"] = row["role"]
            t = int(row["t_ns"])
            if row["event"] == "warp":
                prog["start" if row["phase"] == "start" else "end"] = t
            else:
                prog["events"].append((row["event"], row["phase"], t))
    return launches


def launch_waits(programs, role, tile_start, tile_ready, help_name):
    """Per-launch wait statistics over the GEMM programs of one launch."""
    launch_start = min(p["start"] for p in programs.values())
    per_program = {}
    for pid, prog in programs.items():
        if prog["role"] != role:
            continue
        wait = helped = tiles = 0
        first_wait = None
        pending = help_open = None
        for event, phase, t in sorted(prog["events"], key=lambda e: e[2]):
            if event == tile_start:
                pending = t
            elif event == tile_ready and pending is not None:
                wait += t - pending
                first_wait = t - pending if first_wait is None else first_wait
                tiles += 1
                pending = None
            elif event == help_name and phase == "start":
                help_open = t
            elif event == help_name and phase == "end" and help_open is not None:
                helped += t - help_open
                help_open = None
        per_program[pid] = (wait, helped, tiles, first_wait or 0, prog["end"], prog["start"] - launch_start)
    if not per_program:
        return None
    last = max(per_program, key=lambda p: per_program[p][4])
    span = max(p["end"] for p in programs.values()) - launch_start
    waits = [v[0] for v in per_program.values()]
    return {
        "span": span,
        "b_last": per_program[last][5] + per_program[last][0],
        "pre_last": per_program[last][5],
        "help_last": per_program[last][1],
        "b_mean": statistics.mean(v[5] + v[0] for v in per_program.values()),
        "tile_wait_mean": statistics.mean(waits),
        "help_mean": statistics.mean(v[1] for v in per_program.values()),
        "first_wait": statistics.median(v[3] for v in per_program.values()),
        "units": sum(1 for p in programs.values() for e in p["events"] if e[0] == "unit" and e[1] == "end"),
        "help_units": sum(1 for p in programs.values() for e in p["events"] if e[0] == help_name and e[1] == "end"),
    }


def event_summary(pattern, gemm_role="gemm", tile_start="tile_start", tile_ready="tile_ready", help_name="help"):
    """Median per-launch wait statistics per event table, plus the table of the rank with the longest span."""
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f"no event tables match {pattern!r}")
    per_file = {}
    for path in files:
        stats = [
            s
            for programs in read_events(path).values()
            if (s := launch_waits(programs, gemm_role, tile_start, tile_ready, help_name))
        ]
        if not stats:
            raise SystemExit(f"{path}: no launch has programs with role {gemm_role!r}")
        per_file[path] = {k: statistics.median(s[k] for s in stats) for k in stats[0]} | {"launches": len(stats)}
    slowest = max(per_file, key=lambda p: per_file[p]["span"])
    return per_file[slowest], slowest, per_file


def parse_arm(spec):
    name, *fields = spec.split("|")
    arm = {"name": name, "direct": False}
    for field in fields:
        key, _, value = field.partition("=")
        if key == "direct":
            arm["direct"] = True
        elif key in ("impl", "gemm_cap", "comm", "events", "recorded"):
            arm[key] = value
        else:
            raise SystemExit(f"unknown arm field {key!r} in {spec!r}")
    if "impl" not in arm:
        raise SystemExit(f"arm {spec!r} needs impl=LABEL")
    return arm


def analyze(times, comm, gemm_full, arms, ref_arm=None, mhz=None, event_options=None):
    """Decompose every arm; return (rows, details, clocks) as lists of dicts of numbers, times in ms.

    `times` maps label to median ms, `arms` are `parse_arm` dicts, `mhz(label)` returns the label's busy median SM
    clock or None, and `event_options` holds `event_summary`'s keyword arguments.
    """

    def t(label):
        if label not in times:
            raise SystemExit(f"label {label!r} not timed; labels: {sorted(times)}")
        return times[label]

    mhz = mhz or (lambda label: None)
    g_full = t(gemm_full)
    f_ref = mhz(gemm_full)
    ref_e = None
    if ref_arm:
        ref = next((a for a in arms if a["name"] == ref_arm), None)
        if ref is None:
            raise SystemExit(f"--ref-arm {ref_arm!r} is not an --arm name")
        ref_e = t(ref["impl"]) - g_full
    rows, details, clocks = [], [], []
    for arm in arms:
        c = t(arm.get("comm", comm))
        g_p = t(arm.get("gemm_cap", gemm_full))
        total = t(arm["impl"])
        exposed = total - g_full
        share = g_p - g_full
        direct, source, spin, helped = None, "-", None, None
        if "events" in arm:
            ev, slowest, per_file = event_summary(arm["events"], **(event_options or {}))
            direct, source = ev["b_last"] / 1e6, "events"
            spin, helped = (ev["b_last"] - ev["help_last"]) / 1e6, ev["help_last"] / 1e6
            spans = [v["span"] / 1e6 for v in per_file.values()]
            b_lasts = [v["b_last"] / 1e6 for v in per_file.values()]
            details.append(
                {
                    "arm": arm["name"],
                    "events": os.path.basename(slowest),
                    "launches": ev["launches"],
                    "span": ev["span"] / 1e6,
                    "span_min": min(spans),
                    "span_max": max(spans),
                    "b_last": ev["b_last"] / 1e6,
                    "b_last_min": min(b_lasts),
                    "b_last_max": max(b_lasts),
                    "pre_last": ev["pre_last"] / 1e6,
                    "b_mean": ev["b_mean"] / 1e6,
                    "help_mean": ev["help_mean"] / 1e6,
                    "first_wait_us": ev["first_wait"] / 1e3,
                    "units": ev["units"],
                    "help_units": ev["help_units"],
                }
            )
        elif arm["direct"]:
            direct, source = c, "assumed C"
        row = {
            "arm": arm["name"],
            "C": c,
            "G_full": g_full,
            "G_P": g_p,
            "T": total,
            "E": exposed,
            "a": share,
            "b": direct,
            "b_source": source,
            "b_spin": spin,
            "b_help": helped,
            "c": exposed - share - direct if direct is not None else None,
            "H": 1 - exposed / c,
            "H_P": 1 - (total - g_p) / c,
            "H_max": min(1.0, g_full / c),
            "H_ref": 1 - exposed / ref_e if ref_e else None,
            "rec_ratio": t(arm["recorded"]) / total if "recorded" in arm else None,
        }
        rows.append(row)
        f_t, f_p = mhz(arm["impl"]), mhz(arm.get("gemm_cap", gemm_full))
        if f_ref and f_t and f_p:
            t_n = c + (total - c) * f_t / f_ref if arm["direct"] else total * f_t / f_ref
            e_n, a_n = t_n - g_full, g_p * f_p / f_ref - g_full
            clocks.append(
                {
                    "arm": arm["name"],
                    "f_ref": f_ref,
                    "f_P": f_p,
                    "f_T": f_t,
                    "T_norm": t_n,
                    "E_norm": e_n,
                    "a_norm": a_n,
                    "c_norm": e_n - a_n - direct if direct is not None else None,
                    "H_norm": 1 - e_n / c,
                }
            )
    return rows, details, clocks


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+")
    p.add_argument("--case", required=True)
    p.add_argument("--comm", required=True)
    p.add_argument("--gemm-full", required=True)
    p.add_argument("--arm", action="append", required=True)
    p.add_argument("--ref-arm")
    p.add_argument("--clock-prefix")
    p.add_argument("--busy-watts", type=float, default=200)
    p.add_argument("--clock-tol-mhz", type=float, default=30)
    p.add_argument("--gemm-role", default="gemm")
    p.add_argument("--tile-start", default="tile_start")
    p.add_argument("--tile-ready", default="tile_ready")
    p.add_argument("--help-range", dest="help", default="help")
    p.add_argument("--decimals", type=int, default=3)
    args = p.parse_args()
    case, times, passes = read_times(args.csv, args.case)
    arms = [parse_arm(spec) for spec in args.arm]
    rows, details, clocks = analyze(
        times,
        args.comm,
        args.gemm_full,
        arms,
        ref_arm=args.ref_arm,
        mhz=(lambda label: clock_mhz(args.clock_prefix, label, args.busy_watts)) if args.clock_prefix else None,
        event_options={
            "gemm_role": args.gemm_role,
            "tile_start": args.tile_start,
            "tile_ready": args.tile_ready,
            "help_name": args.help,
        },
    )
    fmt = f"{{:.{args.decimals}f}}"

    def ms(value):
        return fmt.format(value) if value is not None else "-"

    def pct(value):
        return f"{100 * value:.0f}%" if value is not None else "-"

    print(f"## {case}\n")
    print("Times in ms (median of the ABBA passes' medians where present); E = (a) + (b) + (c).\n")
    header = ["arm", "C", "G_full", "G_P", "T", "E", "(a) SM share", "(b) direct", "(b) source", "(c) residual",
              "H", "H_P", "H_max"] + ([f"H_{args.ref_arm}"] if args.ref_arm else [])
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        direct = ms(r["b"])
        if r["b_spin"] is not None:
            direct += f" (spin {ms(r['b_spin'])}, help {ms(r['b_help'])})"
        if r["rec_ratio"] is not None:
            direct += f" (recorded/unrecorded {r['rec_ratio']:.3f}{', OVER 1%' if abs(r['rec_ratio'] - 1) > 0.01 else ''})"
        cells = [r["arm"], ms(r["C"]), ms(r["G_full"]), ms(r["G_P"]), ms(r["T"]), ms(r["E"]), ms(r["a"]), direct,
                 r["b_source"], ms(r["c"]), pct(r["H"]), pct(r["H_P"]), pct(r["H_max"])]
        print("| " + " | ".join(cells + ([pct(r["H_ref"])] if args.ref_arm else [])) + " |")
    if details:
        print("\nDirect exposure from intra-kernel events (ms unless noted; per-launch medians, rank with the longest")
        print("traced span; `last` is the GEMM program that ends last, its wait counts its start delay after the")
        print("launch's first program plus its tile waits; `mean` averages that over GEMM programs):\n")
        dh = ["arm", "events", "launches", "span", "span ranks", "wait last", "wait last ranks", "start delay last",
              "wait mean", "help mean", "first-tile wait us", "self-help units"]
        print("| " + " | ".join(dh) + " |")
        print("|" + "---|" * len(dh))
        for d in details:
            total_units = d["help_units"] + d["units"]
            help_share = (
                f"{100 * d['help_units'] / total_units:.0f}%"
                if d["units"]
                else f"{d['help_units']:.0f} (no producer events)"
            )
            cells = [d["arm"], d["events"], str(d["launches"]), ms(d["span"]),
                     f"{ms(d['span_min'])}..{ms(d['span_max'])}", ms(d["b_last"]),
                     f"{ms(d['b_last_min'])}..{ms(d['b_last_max'])}", ms(d["pre_last"]), ms(d["b_mean"]),
                     ms(d["help_mean"]), fmt.format(d["first_wait_us"]), help_share]
            print("| " + " | ".join(cells) + " |")
    if clocks:
        mismatched = sorted(
            {k["arm"] for k in clocks if max(abs(k["f_T"] - k["f_ref"]), abs(k["f_P"] - k["f_ref"])) > args.clock_tol_mhz}
        )
        if mismatched:
            print(f"\nWARNING: clocks differ from G_full's by more than {args.clock_tol_mhz:.0f} MHz for {mismatched}; "
                  "their E, (c) and H mix clock credit with exposed communication. Rerun below the power cap.")
        print("\nClock-normalized to the G_full clock (reference only; 1/f scaling overcorrected in the controls):\n")
        ch = ["arm", "MHz G_full", "MHz G_P", "MHz T", "T norm", "E norm", "(a) norm", "(c) norm", "H norm"]
        print("| " + " | ".join(ch) + " |")
        print("|" + "---|" * len(ch))
        for k in clocks:
            cells = [k["arm"], f"{k['f_ref']:.0f}", f"{k['f_P']:.0f}", f"{k['f_T']:.0f}", ms(k["T_norm"]),
                     ms(k["E_norm"]), ms(k["a_norm"]), ms(k["c_norm"]), pct(k["H_norm"])]
            print("| " + " | ".join(cells) + " |")
    spread = {label: v for label, v in passes.items() if len(v) > 1}
    if spread:
        print("\nABBA passes per label (ms): " + "; ".join(
            f"{label} {'/'.join(fmt.format(x) for x in v)}" for label, v in sorted(spread.items())))
    print()


if __name__ == "__main__":
    main()
