# /// script
# requires-python = ">=3.10"
# ///
"""Main-stream stalls by cause, and how much side-stream work (copy-engine transfers, NCCL) overlaps compute, per op,
layer and pass, from a torch trace; plus one layer invocation's timeline.

Built for transfers that a side stream runs and the compute stream waits for through CUDA events (copy-engine
all-to-alls, peer copies, collectives on NCCL's stream): the trace shows no wait itself, only a gap on the main stream
that ends when the side-stream work it waited for ends.

Every GPU activity (kernel, memcpy, memset) is joined to its launch (`args["correlation"]`) and labeled by the
innermost host op enclosing the launch whose name matches `--op` (default: any namespaced op outside torch's own
namespaces, e.g. `prime_rl_ep::combine`; `--op-strip` removes module and process-group suffixes), else `-`. An
activity with no launch record, such as the copies of a `cuMemcpyBatchAsync` call (torch 2.14's profiler records one
`Memcpy PtoP` per call, with the call's total bytes, and no driver call), is joined instead through its
`args["External id"]` to the cpu_op that issued it. It gets a segment (layer) and pass from the latest host event on
the launch's thread at or before the launch matching `--segment` (named groups `segment` and `pass`; default FSDP2's
`FSDP::pre_forward (<module>)` / `FSDP::pre_backward (<module>)` hooks). Pass is backward if that text contains
"backward"; a backward activity whose op matches `--recompute-op` becomes pass `recompute` (activation checkpointing
replays). The main stream is the stream with the most kernel time outside `--comm`.

Stalls: every gap of at least `--min-gap-us` between consecutive main-stream activities is split into
- `host`: the part before the next activity's launch call began (the GPU had nothing queued; host-bound or a host
  sync), and
- `wait:<kind>:<op>` for the rest when a side-stream activity ended within `--match-us` before the next activity
  started (the latest-ending one; kind is `memcpy`, `nccl` or `kernel`), else `other`.
A gap is booked to the pass and segment of the activity after it, and labeled `<last labeled op before> > <op
after>`, which locates it between two ops (e.g. the host gap after a dispatch, before the GEMM that waits for it).
Communication kernels that run on the main stream (e.g. a small all-to-all) are not gaps; they get their own table
(count, ms, p50/p90/max per call; with `--per-segment`, mean and max per segment), since their time includes waiting
for the slowest peer.

Side-stream overlap: per side-stream activity matching `--side` (default: memcpys and `--comm` kernels), its
duration, the part covered by main-stream compute (main-stream kernels not matching `--comm`), and the exposed part
(no compute kernel on any stream). Transfer time that the main stream did not wait for costs nothing even when exposed;
the stalls are the cost.

Window: the whole trace, or from the `--annotation-index`th CPU-side `user_annotation` named `--annotation` (also
`<name>#<n>`) to the start of the next one matching `--end-annotation`, selected by launch time. `--steps N` divides
the totals by N.

`--during REGEX` adds, per pass and cause kind (host, wait:memcpy, wait:nccl, ...), how much of the stall time a
side-stream activity matching REGEX was running: a metric that counts a GPU as busy whenever any kernel runs books
such stalls as that activity's exposed time (e.g. a copy-engine wait read as exposed FSDP all-gather).

`--timeline REGEX` prints every activity of the `--timeline-index`th invocation of a segment whose name matches REGEX
in pass `--timeline-pass` (forward or backward; a backward invocation includes its recompute): offset from its first
activity, duration, stream (main or side), pass, op, kernel name, and each main-stream gap with its cause. `--csv P`
writes `P_stalls.csv` (one row per gap), `P_side.csv` (one row per side activity), `P_main_comm.csv` (one row
per main-stream communication kernel) and, with `--timeline`, `P_timeline.csv`; `--json` writes the totals.

Usage:
  uv run --script stream_stalls.py <trace.json.gz> [--annotation forward --annotation-index -4]
    [--end-annotation '^Optimizer\\.step'] [--steps 1] [--comm '^nccl'] [--op REGEX] [--segment REGEX]
    [--recompute-op REGEX] [--side REGEX] [--min-gap-us 2] [--match-us 30] [--per-segment] [--during REGEX]
    [--timeline 'model\\.layers\\.12$' --timeline-index -1 --timeline-pass backward] [--csv PREFIX] [--json out.json]
  prime-pt copy-engine MoE: --recompute-op 'prime_rl_ep::(dispatch|dispatch_routes|gate_up|down|combine)$|all_to_all_single_equal|host_copy'
"""

import argparse
import bisect
import csv
import json
import re
import sys
from collections import defaultdict

from top_kernels import GPU_CATS, short_name
from trace_events import LAUNCH_CATEGORIES, is_marker, launch_stacks, latest_marks, read_trace

DEFAULT_OP = r"^(?!aten::|c10d::|cuda::|profiler::|autograd::|torch::|Torch-Compiled|CompiledFunction)\w+::\w+"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("trace")
    p.add_argument("--annotation", default=None)
    p.add_argument("--annotation-index", type=int, default=-1)
    p.add_argument("--end-annotation", default=r"^Optimizer\.step")
    p.add_argument("--steps", type=float, default=1.0)
    p.add_argument("--comm", default=r"^nccl", help="regex of communication kernel names (not compute)")
    p.add_argument("--op", default=DEFAULT_OP, help="regex of host ops that label an activity (innermost wins)")
    p.add_argument("--op-strip", default=r"\s*[\[(].*$", help="regex removed from op labels (module, group suffixes)")
    p.add_argument("--segment", default=r"^FSDP::pre_(?P<pass>forward|backward) \((?P<segment>[^)]*)\)")
    p.add_argument("--recompute-op", default=None, help="regex: backward activities under these ops are recompute")
    p.add_argument("--side", default=None, help="regex of side-stream activity names to report (default memcpys + comm)")
    p.add_argument("--min-gap-us", type=float, default=2.0)
    p.add_argument("--match-us", type=float, default=30.0)
    p.add_argument("--during", default=None,
                   help="regex of side-stream activity names: report how much of each stall cause overlaps them")
    p.add_argument("--per-segment", action="store_true", help="also print totals per segment")
    p.add_argument("--timeline", default=None, help="regex of the segment whose invocation to print")
    p.add_argument("--timeline-index", type=int, default=-1)
    p.add_argument("--timeline-pass", default="forward", choices=("forward", "backward"))
    p.add_argument("--csv", default=None)
    p.add_argument("--json", default=None)
    return p.parse_args()


def merge(intervals):
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def covered(lo, hi, merged, starts):
    """Length of [lo, hi) inside the merged intervals (``starts`` their start times)."""
    total = 0.0
    i = max(bisect.bisect_right(starts, lo) - 1, 0)
    while i < len(merged) and merged[i][0] < hi:
        total += max(0.0, min(hi, merged[i][1]) - max(lo, merged[i][0]))
        i += 1
    return total


def kind(name, comm):
    if name.startswith("Memcpy"):
        return "memcpy"
    if name.startswith("Memset"):
        return "memset"
    return "nccl" if comm.search(name) else "kernel"


def main():
    args = parse_args()
    comm, op_re, seg_re = re.compile(args.comm), re.compile(args.op), re.compile(args.segment)
    strip_re = re.compile(args.op_strip)
    recompute_re = re.compile(args.recompute_op) if args.recompute_op else None
    side_re = re.compile(args.side) if args.side else None
    events = [e for e in read_trace(args.trace)["traceEvents"] if e.get("ph") == "X"]
    launches = {e["args"]["correlation"]: e for e in events
                if e.get("cat") in LAUNCH_CATEGORIES and "correlation" in e.get("args", {})}
    gpu = [e for e in events if e.get("cat") in GPU_CATS and "dur" in e]
    ops_by_external = {e["args"]["External id"]: e for e in events
                       if e.get("cat") == "cpu_op" and "External id" in e.get("args", {})}
    for i, e in enumerate(gpu):
        if e.get("args", {}).get("correlation") not in launches:
            op = ops_by_external.get(e.get("args", {}).get("External id"))
            if op is not None:
                proxy = {"ph": "X", "cat": "cuda_runtime", "name": "external id", "pid": op["pid"], "tid": op["tid"],
                         "ts": op["ts"], "dur": 0, "args": {"correlation": ("external", i)}}
                events.append(proxy)
                launches[proxy["args"]["correlation"]] = proxy
                e.setdefault("args", {})["correlation"] = proxy["args"]["correlation"]
    lo, hi = float("-inf"), float("inf")
    if args.annotation:
        marks = sorted((e for e in events if e.get("cat") == "user_annotation" and is_marker(e["name"], args.annotation)),
                       key=lambda e: e["ts"])
        if not marks:
            sys.exit(f"no user_annotation named {args.annotation}")
        lo = marks[args.annotation_index]["ts"]
        end_re = re.compile(args.end_annotation)
        hi = min((e["ts"] for e in events if e.get("cat") == "user_annotation" and e["ts"] > lo
                  and end_re.search(e["name"])), default=float("inf"))
    acts = []
    for e in gpu:
        launch = launches.get(e.get("args", {}).get("correlation"))
        if launch is None or not lo <= launch["ts"] < hi:
            continue
        acts.append(e | {"launch": launch, "kind": kind(e["name"], comm), "stream": (e["pid"], e["tid"])})
    if not acts:
        sys.exit("no GPU activity launched in the window")
    correlations = {a["args"]["correlation"] for a in acts}
    stacks = launch_stacks(events, correlations)
    marks = latest_marks(events, correlations, seg_re)
    for a in acts:
        c = a["args"]["correlation"]
        a["op"] = next((strip_re.sub("", h["name"]) for h in reversed(stacks.get(c, [])) if op_re.search(h["name"])), "-")
        mark = marks.get(c)
        if mark is None:
            a["segment"], a["pass"], a["inv"] = "-", "-", None
        else:
            event, found = mark
            a["segment"] = found.groupdict().get("segment") or event["name"]
            a["pass"] = "backward" if "backward" in (found.groupdict().get("pass") or event["name"]) else "forward"
            a["inv"] = (event["ts"], event["tid"], a["segment"], a["pass"])
            if a["pass"] == "backward" and recompute_re and recompute_re.search(a["op"]):
                a["pass"] = "recompute"
    per_stream = defaultdict(float)
    for a in acts:
        if a["kind"] == "kernel":
            per_stream[a["stream"]] += a["dur"]
    main_stream = max(per_stream, key=per_stream.get)
    main = sorted((a for a in acts if a["stream"] == main_stream), key=lambda a: a["ts"])
    side = sorted((a for a in acts if a["stream"] != main_stream), key=lambda a: a["ts"] + a["dur"])
    side_ends = [a["ts"] + a["dur"] for a in side]
    main_compute = merge([(a["ts"], a["ts"] + a["dur"]) for a in main if a["kind"] == "kernel"])
    any_compute = merge([(a["ts"], a["ts"] + a["dur"]) for a in acts if a["kind"] == "kernel"])
    mc_starts, ac_starts = [m[0] for m in main_compute], [m[0] for m in any_compute]

    stalls = []
    prev_end = main[0]["ts"] + main[0]["dur"]
    prev_op = main[0]["op"]
    for b in main[1:]:
        gap = b["ts"] - prev_end
        if gap >= args.min_gap_us:
            host = min(max(b["launch"]["ts"] - prev_end, 0.0), gap)
            cause, rest = "other", gap - host
            if rest > 0:
                j = bisect.bisect_right(side_ends, b["ts"]) - 1
                best = None
                while j >= 0 and side_ends[j] >= b["ts"] - args.match_us:
                    if side_ends[j] > prev_end:
                        best = side[j]
                        break
                    j -= 1
                if best is not None:
                    cause = f"wait:{best['kind']}:{best['op']}"
            stalls.append({"start": prev_end, "gap": gap, "host": host, "rest": rest, "cause": cause,
                           "pass": b["pass"], "segment": b["segment"], "op": f"{prev_op} > {b['op']}", "next": short_name(b["name"]),
                           "inv": b["inv"]})
        prev_end = max(prev_end, b["ts"] + b["dur"])
        if b["op"] != "-":
            prev_op = b["op"]

    report_side = [a for a in side if (side_re.search(a["name"]) if side_re else a["kind"] in ("memcpy", "nccl"))]
    for a in report_side:
        s, e = a["ts"], a["ts"] + a["dur"]
        a["covered"] = covered(s, e, main_compute, mc_starts)
        a["exposed"] = a["dur"] - covered(s, e, any_compute, ac_starts)

    if args.during:
        during_re = re.compile(args.during)
        during = merge([(a["ts"], a["ts"] + a["dur"]) for a in side if during_re.search(a["name"])])
        d_starts = [m[0] for m in during]
        for s_ in stalls:
            s_["during_host"] = covered(s_["start"], s_["start"] + s_["host"], during, d_starts)
            s_["during_rest"] = covered(s_["start"] + s_["host"], s_["start"] + s_["gap"], during, d_starts)

    n = args.steps
    out = {"trace": args.trace, "main_stream": list(main_stream), "steps": n, "stalls": {}, "side": {}}
    stall_tot = defaultdict(lambda: [0, 0.0])
    for s in stalls:
        if s["host"] > 0:
            stall_tot[(s["pass"], "host", s["op"])][0] += 1
            stall_tot[(s["pass"], "host", s["op"])][1] += s["host"]
        if s["rest"] > 0:
            stall_tot[(s["pass"], s["cause"], s["op"])][0] += 1
            stall_tot[(s["pass"], s["cause"], s["op"])][1] += s["rest"]
    print(f"# {args.trace}\nmain stream {main_stream}, window launches {len(acts)}, per step = totals / {n:g}\n")
    print("## Main-stream stalls (ms per step), by pass, cause, and the last labeled op before > the op after\n")
    print("| pass | cause | ops | gaps | ms |\n|---|---|---|---|---|")
    for (ps, cause, op), (cnt, t) in sorted(stall_tot.items(), key=lambda kv: (kv[0][0], -kv[1][1])):
        if t / n >= 0.05:
            print(f"| {ps} | {cause} | {op} | {cnt / n:.0f} | {t / n / 1e3:.2f} |")
        out["stalls"][f"{ps}|{cause}|{op}"] = {"gaps": cnt / n, "ms": t / n / 1e3}
    by_pass = defaultdict(lambda: defaultdict(float))
    for (ps, cause, _), (_, t) in stall_tot.items():
        by_pass[ps][cause.split(":")[0]] += t / n / 1e3
    print("\n| pass | host ms | wait ms | other ms |\n|---|---|---|---|")
    for ps, d in sorted(by_pass.items()):
        print(f"| {ps} | {d['host']:.2f} | {d['wait']:.2f} | {d['other']:.2f} |")
    out["stalls_by_pass"] = {ps: dict(d) for ps, d in by_pass.items()}
    if args.during:
        dur_tot = defaultdict(lambda: [0.0, 0.0])
        for s_ in stalls:
            dur_tot[(s_["pass"], "host")][0] += s_["host"]
            dur_tot[(s_["pass"], "host")][1] += s_["during_host"]
            key = (s_["pass"], ":".join(s_["cause"].split(":")[:2]))
            dur_tot[key][0] += s_["rest"]
            dur_tot[key][1] += s_["during_rest"]
        print(f"\n## Stall time during side activity matching `{args.during}` (ms per step)\n")
        print("| pass | cause | stall ms | of which during |\n|---|---|---|---|")
        for (ps, c), (t, d) in sorted(dur_tot.items()):
            print(f"| {ps} | {c} | {t / n / 1e3:.2f} | {d / n / 1e3:.2f} |")
        out["during"] = {f"{ps}|{c}": {"stall_ms": t / n / 1e3, "during_ms": d / n / 1e3}
                         for (ps, c), (t, d) in dur_tot.items()}

    main_comm = defaultdict(list)
    for a in main:
        if a["kind"] == "nccl":
            main_comm[(a["pass"], a["op"])].append(a["dur"])
    if main_comm:
        print("\n## Communication kernels on the main stream (ms per step; their time includes waiting for peers)\n")
        print("| pass | op | count | ms | p50 us | p90 us | max us |\n|---|---|---|---|---|---|---|")
        for (ps, op), durs in sorted(main_comm.items(), key=lambda kv: -sum(kv[1])):
            d = sorted(durs)
            print(f"| {ps} | {op} | {len(d) / n:.0f} | {sum(d) / n / 1e3:.2f} | {d[len(d) // 2]:.0f} | "
                  f"{d[int(0.9 * (len(d) - 1))]:.0f} | {d[-1]:.0f} |")
    if main_comm and args.per_segment:
        per_seg = defaultdict(list)
        for a in main:
            if a["kind"] == "nccl":
                per_seg[(a["segment"], a["pass"])].append(a["dur"])
        print("\n| segment | pass | count | mean us | max us |\n|---|---|---|---|---|")
        for (sg, ps), d in sorted(per_seg.items()):
            print(f"| {sg} | {ps} | {len(d)} | {sum(d) / len(d):.0f} | {max(d):.0f} |")
    out["main_comm"] = {f"{ps}|{op}": {"count": len(d) / n, "ms": sum(d) / n / 1e3, "p50_us": sorted(d)[len(d) // 2]}
                        for (ps, op), d in main_comm.items()}

    side_tot = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for a in report_side:
        t = side_tot[(a["pass"], a["kind"], a["op"])]
        t[0] += 1
        t[1] += a["dur"]
        t[2] += a["covered"]
        t[3] += a["exposed"]
    print("\n## Side-stream activity (ms per step): covered by main-stream compute, exposed (no compute anywhere)\n")
    print("| pass | kind | op | count | ms | covered ms | exposed ms |\n|---|---|---|---|---|---|---|")
    for (ps, k, op), (cnt, d, c, x) in sorted(side_tot.items(), key=lambda kv: (kv[0][0], -kv[1][1])):
        if d / n >= 0.05:
            print(f"| {ps} | {k} | {op} | {cnt / n:.0f} | {d / n / 1e3:.2f} | {c / n / 1e3:.2f} | {x / n / 1e3:.2f} |")
        out["side"][f"{ps}|{k}|{op}"] = {"count": cnt / n, "ms": d / n / 1e3, "covered_ms": c / n / 1e3,
                                          "exposed_ms": x / n / 1e3}

    if args.per_segment:
        seg = defaultdict(lambda: defaultdict(float))
        for s in stalls:
            seg[(s["segment"], s["pass"])]["host"] += s["host"]
            seg[(s["segment"], s["pass"])][s["cause"].split(":")[0]] += s["rest"]
        print("\n## Stalls per segment and pass (ms per step)\n")
        print("| segment | pass | host | wait | other |\n|---|---|---|---|---|")
        for (sg, ps), d in sorted(seg.items()):
            print(f"| {sg} | {ps} | {d['host'] / n / 1e3:.3f} | {d['wait'] / n / 1e3:.3f} | {d['other'] / n / 1e3:.3f} |")
        out["per_segment"] = {f"{sg}|{ps}": {k: v / n / 1e3 for k, v in d.items()} for (sg, ps), d in seg.items()}

    rows = None
    if args.timeline:
        tl_re = re.compile(args.timeline)
        invs = sorted({a["inv"] for a in acts if a["inv"] and tl_re.search(a["inv"][2])
                       and a["inv"][3] == args.timeline_pass}, key=lambda i: i[0])
        if not invs:
            sys.exit(f"no {args.timeline_pass} invocation of a segment matching {args.timeline}")
        inv = invs[args.timeline_index]
        mine = sorted((a for a in acts if a["inv"] == inv), key=lambda a: a["ts"])
        t0 = mine[0]["ts"]
        gaps = {s["start"]: s for s in stalls if s["inv"] == inv}
        rows = []
        for a in mine:
            where = "main" if a["stream"] == main_stream else f"side:{a['tid']}"
            rows.append({"t_us": round(a["ts"] - t0, 1), "dur_us": round(a["dur"], 1), "stream": where,
                         "pass": a["pass"], "op": a["op"], "name": short_name(a["name"])[:70]})
        for s in gaps.values():
            rows.append({"t_us": round(s["start"] - t0, 1), "dur_us": round(s["gap"], 1), "stream": "main-gap",
                         "pass": s["pass"], "op": s["op"],
                         "name": f"host {s['host']:.0f} us, {s['cause']} {s['rest']:.0f} us"})
        rows.sort(key=lambda r: r["t_us"])
        print(f"\n## Timeline: {inv[2]} {inv[3]} (invocation {args.timeline_index} of {len(invs)})\n")
        print("| t us | dur us | stream | pass | op | name |\n|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['t_us']} | {r['dur_us']} | {r['stream']} | {r['pass']} | {r['op']} | {r['name']} |")

    if args.csv:
        with open(f"{args.csv}_stalls.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start_us", "gap_us", "host_us", "rest_us", "cause", "pass", "segment", "op", "next"])
            for s in stalls:
                w.writerow([s["start"], s["gap"], s["host"], s["rest"], s["cause"], s["pass"], s["segment"], s["op"],
                            s["next"]])
        with open(f"{args.csv}_side.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start_us", "dur_us", "covered_us", "exposed_us", "kind", "pass", "segment", "op", "name"])
            for a in report_side:
                w.writerow([a["ts"], a["dur"], a["covered"], a["exposed"], a["kind"], a["pass"], a["segment"], a["op"],
                            a["name"]])
        with open(f"{args.csv}_main_comm.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start_us", "dur_us", "pass", "segment", "op", "name"])
            for a in main:
                if a["kind"] == "nccl":
                    w.writerow([a["ts"], a["dur"], a["pass"], a["segment"], a["op"], a["name"]])
        if rows is not None:
            with open(f"{args.csv}_timeline.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
