# /// script
# requires-python = ">=3.10"
# ///
"""Named intervals between intra-kernel events, per CTA and iteration, as narrow markdown tables.

Reads one or more tidy event tables from `intra_kernel_events.py` (concatenated, keyed by their `variant`
column) and builds intervals from event pairs. An interval spec is `NAME=START:END`, where START and END are
event references:

- `name` for a point event (`phase` `mark`), `name.start` / `name.end` for the ends of a range, and
  `warp.start` / `warp.end` for a warp's lifetime.
- An optional `@wN` (warp N) or `@ROLE` (the lowest-numbered warp with that role) selector. Without
  selectors, the interval is measured within each warp separately, one sample per warp. With them, it is one
  sample per CTA.

Iterations are counted per warp: the k-th occurrence of an event in a warp belongs to iteration k, so START
and END pair up by occurrence number. That suits loops that emit each event once per iteration, such as a
persistent kernel's work loop (iteration 0 is each CTA's first work item) or a non-persistent kernel's
single pass (iteration 0 only). Iteration 0 is reported apart from the rest (`first` / `steady`), because a
persistent CTA's first item runs from a cold start and behaves like a non-persistent CTA.

For each variant, interval and iteration class the table gives the sample count and the median, p20 and
p80 in microseconds (lower is better for every duration). `--gate NAME=I1,I2,...` reports, per iteration,
which of the listed intervals (usually waits) was longest: the fraction of samples each one dominated and
its median length there. Samples where every listed interval is at most `--gate-floor-ns` (default 64 ns,
two 32 ns ticks) count as `none`, since a wait that short only says the data had already arrived.
`--sm-gaps` adds, per variant, the idle time on an SM between one CTA's last warp exit and the next CTA's
first warp start (non-persistent grids). When CTAs share an SM, only time with no CTA resident counts as a
gap, and the last column gives the most CTAs seen on one SM at once. `--spans` adds each launch's span, first
warp start to last warp exit, the traced counterpart of the kernel's duration. `--crowding NAME` asks whether
an interval (usually a load's issue to its arrival) gets longer when many CTAs run it at once: for each sample
it counts the samples of that interval, anywhere in the same launch, that have started and not yet ended at its
start (itself included), then reports the median duration per count bucket (`--crowding-buckets`, default
20,40,60,100) and the median number of other starts within `--crowding-window-ns` (default 250) of each start.
`--csv` also writes every sample.

Usage:
  uv run --script intra_kernel_intervals.py np_tma.events.csv.gz p_tma.events.csv.gz \\
      --interval q_wait=c_wait_q@w0:c_q_ready@w0 --interval k_wait=c_wait_k@w0:c_k_ready@w0 \\
      --gate first_gemm=q_wait,k_wait --sm-gaps
"""

import argparse
import bisect
import csv
import gzip
import statistics
import sys
from collections import defaultdict


def read_events(paths: list[str]):
    """{variant: {(launch, cta): {warp: {event_ref: [t_ns, ...]}}}} plus {variant: {warp: role}} and SM placement."""
    events = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    roles = defaultdict(dict)
    placement = defaultdict(dict)
    source = {}
    for path in paths:
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt", newline="") as f:
            for row in csv.DictReader(f):
                ref = row["event"] if row["phase"] == "mark" else f"{row['event']}.{row['phase']}"
                key = (int(row["launch"]), int(row["cta"]))
                if source.setdefault((row["variant"], key[0]), path) != path:
                    raise SystemExit(
                        f"{path} and {source[row['variant'], key[0]]} both hold variant {row['variant']!r}"
                        f" launch {key[0]}; give each run its own --variant"
                    )
                warp = int(row["warp"])
                events[row["variant"]][key][warp][ref].append(int(row["t_ns"]))
                roles[row["variant"]][warp] = row["role"]
                placement[row["variant"]][key] = int(row["sm"])
    for variant in events:
        for cta in events[variant].values():
            for refs in cta.values():
                for times in refs.values():
                    times.sort()
    return events, roles, placement


def parse_ref(text: str) -> tuple[str, str | None]:
    name, _, selector = text.partition("@")
    return name, selector or None


def resolve_warp(selector: str | None, roles: dict[int, str]) -> int | None:
    if selector is None:
        return None
    if selector.startswith("w") and selector[1:].isdigit():
        return int(selector[1:])
    matches = sorted(w for w, role in roles.items() if role == selector)
    if not matches:
        raise SystemExit(f"no warp has role {selector!r}; roles: {sorted(set(roles.values()))}")
    return matches[0]


def interval_samples(events, roles, spec: str):
    """[(variant, launch, cta, warp, iteration, duration_ns, start_ns)] for one `NAME=START:END` spec."""
    name, _, body = spec.partition("=")
    if body.count(":") != 1:
        raise SystemExit(f"interval {spec!r} is not NAME=START:END")
    start_text, end_text = body.split(":")
    (start_ref, start_sel), (end_ref, end_sel) = parse_ref(start_text), parse_ref(end_text)
    samples = []
    unpaired = negative = 0
    for variant, ctas in events.items():
        start_warp, end_warp = resolve_warp(start_sel, roles[variant]), resolve_warp(end_sel, roles[variant])
        for (launch, cta), warps in ctas.items():
            pairs = []
            if start_warp is None and end_warp is None:
                pairs = [(w, refs.get(start_ref, []), refs.get(end_ref, [])) for w, refs in warps.items()]
            else:
                sw = start_warp if start_warp is not None else end_warp
                ew = end_warp if end_warp is not None else start_warp
                pairs = [(sw, warps.get(sw, {}).get(start_ref, []), warps.get(ew, {}).get(end_ref, []))]
            for warp, starts, ends in pairs:
                unpaired += len(starts) != len(ends)
                for iteration, (t_start, t_end) in enumerate(zip(starts, ends)):
                    negative += t_end < t_start
                    samples.append((variant, launch, cta, warp, iteration, t_end - t_start, t_start))
    if unpaired:
        print(
            f"note: interval {name}: START and END counts differ in {unpaired} warps or CTAs, which pair only their"
            " first occurrences, in order: expected for a one-off event such as an init, otherwise a missing event"
            " shifts every later pair",
            file=sys.stderr,
        )
    if negative:
        print(
            f"warning: interval {name}: {negative} samples end before they start (mispaired or wrapped clock)",
            file=sys.stderr,
        )
    return name, samples


def quantiles(values: list[float]) -> tuple[float, float, float]:
    if len(values) == 1:
        return values[0], values[0], values[0]
    p20, _, _, p80 = statistics.quantiles(values, n=5, method="inclusive")
    return statistics.median(values), p20, p80


def iteration_class(iteration: int) -> str:
    return "first" if iteration == 0 else "steady"


def print_interval_table(results: dict[str, list]) -> None:
    print("\nintervals in µs (lower is better): median [p20, p80], n samples\n")
    print("| variant | interval | iter | n | median | p20 | p80 |")
    print("|---|---|---|---|---|---|---|")
    for name, samples in results.items():
        groups = defaultdict(list)
        for variant, _, _, _, iteration, duration, _ in samples:
            groups[(variant, iteration_class(iteration))].append(duration / 1e3)
        for (variant, klass), values in sorted(groups.items()):
            median, p20, p80 = quantiles(values)
            print(f"| {variant} | {name} | {klass} | {len(values)} | {median:.3f} | {p20:.3f} | {p80:.3f} |")


def print_gate_table(spec: str, results: dict[str, list], floor_ns: int) -> None:
    name, _, members = spec.partition("=")
    members = members.split(",")
    by_key = defaultdict(dict)
    for member in members:
        if member not in results:
            raise SystemExit(f"--gate {name} names {member!r}, which is not an --interval")
        for variant, launch, cta, warp, iteration, duration, _ in results[member]:
            by_key[(variant, launch, cta, warp, iteration)][member] = duration
    tallies = defaultdict(lambda: defaultdict(list))
    for (variant, _, _, _, iteration), durations in by_key.items():
        if len(durations) != len(members):
            continue
        winner, longest = max(durations.items(), key=lambda kv: kv[1])
        tallies[(variant, iteration_class(iteration))]["none" if longest <= floor_ns else winner].append(longest / 1e3)
    print(f"\n{name}: which interval was longest per sample (share of samples, median µs when it was longest)\n")
    print("| variant | iter | gate | share | median µs |")
    print("|---|---|---|---|---|")
    for (variant, klass), winners in sorted(tallies.items()):
        total = sum(len(v) for v in winners.values())
        for winner, values in sorted(winners.items(), key=lambda kv: -len(kv[1])):
            print(f"| {variant} | {klass} | {winner} | {len(values) / total:.1%} | {statistics.median(values):.3f} |")


def print_sm_gaps(events, placement) -> None:
    print("\nidle time on an SM between consecutive CTAs, µs (lower is better)\n")
    print("| variant | n gaps | median | p20 | p80 | CTAs per SM (median) | CTAs at once (max) |")
    print("|---|---|---|---|---|---|---|")
    for variant, ctas in sorted(events.items()):
        spans = defaultdict(list)
        for key, warps in ctas.items():
            starts = [t for refs in warps.values() for t in refs.get("warp.start", [])]
            ends = [t for refs in warps.values() for t in refs.get("warp.end", [])]
            if starts and ends:
                spans[(key[0], placement[variant][key])].append((min(starts), max(ends)))
        gaps, counts, resident = [], [], 1
        for intervals in spans.values():
            intervals.sort()
            counts.append(len(intervals))
            busy_until, ends = intervals[0][1], []
            for start, end in intervals:
                ends = [e for e in ends if e > start] + [end]
                resident = max(resident, len(ends))
                if start > busy_until:
                    gaps.append((start - busy_until) / 1e3)
                busy_until = max(busy_until, end)
        if counts:
            median, p20, p80 = (f"{q:.3f}" for q in quantiles(gaps)) if gaps else ("-", "-", "-")
            print(
                f"| {variant} | {len(gaps)} | {median} | {p20} | {p80} | {statistics.median(counts):.0f} | {resident} |"
            )


def print_spans(events) -> None:
    print("\nlaunch span, first warp start to last warp exit, µs (lower is better)\n")
    print("| variant | launch | span |")
    print("|---|---|---|")
    for variant, ctas in sorted(events.items()):
        first, last = {}, {}
        for (launch, _), warps in ctas.items():
            for refs in warps.values():
                for t in refs.get("warp.start", []):
                    first[launch] = min(first.get(launch, t), t)
                for t in refs.get("warp.end", []):
                    last[launch] = max(last.get(launch, t), t)
        for launch in sorted(first):
            print(f"| {variant} | {launch} | {(last[launch] - first[launch]) / 1e3:.1f} |")


def print_crowding(name: str, samples: list, buckets: list[int], window_ns: int) -> None:
    edges = [0, *buckets]
    labels = [f"{lo}-{hi - 1}" for lo, hi in zip(edges, edges[1:])] + [f"{edges[-1]} or more"]
    by_launch = defaultdict(list)
    for variant, launch, _, _, _, duration, start in samples:
        by_launch[(variant, launch)].append((start, start + duration))
    rows = defaultdict(lambda: defaultdict(list))
    nearby = defaultdict(list)
    for (variant, _), spans in by_launch.items():
        starts = sorted(s for s, _ in spans)
        ends = sorted(e for _, e in spans)
        for start, end in spans:
            in_flight = bisect.bisect_right(starts, start) - bisect.bisect_right(ends, start)
            rows[variant][bisect.bisect_right(buckets, in_flight)].append((end - start) / 1e3)
            close = bisect.bisect_right(starts, start + window_ns) - bisect.bisect_left(starts, start - window_ns)
            nearby[variant].append(close - 1)
    print(f"\n{name} by how many samples of it were in flight at its start, µs (lower is better)\n")
    print("| variant | in flight | n | median | others starting within ±window (median) |")
    print("|---|---|---|---|---|")
    for variant in sorted(rows):
        crowd = statistics.median(nearby[variant])
        for index in sorted(rows[variant]):
            values = rows[variant][index]
            print(f"| {variant} | {labels[index]} | {len(values)} | {statistics.median(values):.3f} | {crowd:.0f} |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("events", nargs="+", help="tidy event CSVs from intra_kernel_events.py")
    parser.add_argument("--interval", action="append", default=[], help="NAME=START:END, repeatable")
    parser.add_argument("--gate", action="append", default=[], help="NAME=INTERVAL,INTERVAL,..., repeatable")
    parser.add_argument("--gate-floor-ns", type=int, default=64)
    parser.add_argument("--sm-gaps", action="store_true")
    parser.add_argument("--spans", action="store_true")
    parser.add_argument("--crowding", action="append", default=[], help="an --interval NAME, repeatable")
    parser.add_argument("--crowding-buckets", default="20,40,60,100")
    parser.add_argument("--crowding-window-ns", type=int, default=250)
    parser.add_argument("--csv", help="also write every interval sample here")
    args = parser.parse_args()

    events, roles, placement = read_events(args.events)
    results = dict(interval_samples(events, roles, spec) for spec in args.interval)
    for name, samples in results.items():
        if not samples:
            print(f"warning: interval {name} matched no events", file=sys.stderr)
    print_interval_table(results)
    for spec in args.gate:
        print_gate_table(spec, results, args.gate_floor_ns)
    if args.sm_gaps:
        print_sm_gaps(events, placement)
    if args.spans:
        print_spans(events)
    buckets = [int(b) for b in args.crowding_buckets.split(",")]
    for name in args.crowding:
        if name not in results:
            raise SystemExit(f"--crowding names {name!r}, which is not an --interval")
        print_crowding(name, results[name], buckets, args.crowding_window_ns)
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(("interval", "variant", "launch", "cta", "warp", "iteration", "duration_ns", "start_ns"))
            for name, samples in results.items():
                writer.writerows((name, *sample) for sample in samples)


if __name__ == "__main__":
    main()
