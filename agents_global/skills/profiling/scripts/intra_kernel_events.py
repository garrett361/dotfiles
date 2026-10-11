"""Convert an intra-kernel trace into the recorder-agnostic tidy event table the other `intra_kernel_*` scripts read.

The table is a CSV (gzipped if the name ends in `.gz`) with one row per recorded event:

| column  | meaning                                                                                 |
|---------|-----------------------------------------------------------------------------------------|
| variant | free label for the kernel version (`--variant`), so tables from several runs concatenate |
| launch  | index of the kernel launch within the trace, in launch order                             |
| sm      | SM id the warp ran on                                                                    |
| cta     | linear CTA id, `x + y * gridDimX + z * gridDimX * gridDimY`                              |
| warp    | warp id within the CTA                                                                   |
| role    | warp role from `--roles` (e.g. `producer`), or `warp<N>` when unmapped                   |
| event   | event name, or `warp` for the recorder's own warp lifetime                              |
| phase   | `mark` for a point event, `start` or `end` for the two ends of a range or a lifetime      |
| t_ns    | nanoseconds since the earliest warp start of that launch                                 |
| payload | the event's integer or float payload, empty when it has none                             |

Any recorder that can write these columns plugs into `intra_kernel_intervals.py` and
`intra_kernel_ab_figure.py` unchanged. This script reads IKET (`run-iket ... --postprocess json`, CuTe DSL
4.7.1): markers become `mark` rows, token and push/pop ranges become a `start` and an `end` row (each from
the warp that emitted it), and `warpLifetimes` become `warp` rows. Timestamps keep IKET's 32 ns granularity.

`--roles` maps warp ids to roles as `name:first-last` pairs, e.g. for a 384-thread kernel with two consumer
warpgroups and a producer warpgroup: `consumer0:0-3,consumer1:4-7,producer:8-11`. `--launches` picks launches
by index (default `-1`, the last one, since the first launch of a process often runs cold).

Usage:
  python3 intra_kernel_events.py iket_pid_0x1234.trace.json --variant p_tma \\
      --roles consumer0:0-3,consumer1:4-7,producer:8-11 --out p_tma.events.csv.gz [--launches 1 2]
"""

import argparse
import csv
import gzip
import json
import sys

COLUMNS = ("variant", "launch", "sm", "cta", "warp", "role", "event", "phase", "t_ns", "payload")


def parse_roles(spec: str) -> dict[int, str]:
    roles = {}
    for part in filter(None, spec.split(",")):
        name, span = part.split(":")
        first, _, last = span.partition("-")
        for warp in range(int(first), int(last or first) + 1):
            roles[warp] = name
    return roles


def iket_launches(trace: dict) -> list[dict]:
    launches = list(trace.get("launches", []))
    for graph_launches in trace.get("graphLaunches", {}).values():
        launches.extend(graph_launches)
    return launches


def iket_rows(trace: dict, launch_indices: list[int], variant: str, roles: dict[int, str]):
    names = trace["stringTable"]
    locations = trace["locationTable"]
    launches = iket_launches(trace)
    for launch_index in sorted({i % len(launches) for i in launch_indices}):
        launch = launches[launch_index]
        grid_x, grid_y = launch["gridDimX"], launch["gridDimY"]
        t0 = min(w["startTs"] for w in launch["warpLifetimes"])

        def where(loc_idx: int) -> tuple:
            loc = locations[loc_idx]
            x, y, z = loc["ctaId"]
            warp = loc["warpId"]
            return loc["smId"], x + y * grid_x + z * grid_x * grid_y, warp, roles.get(warp, f"warp{warp}")

        for w in launch["warpLifetimes"]:
            here = where(w["locIdx"])
            yield (variant, launch_index, *here, "warp", "start", w["startTs"] - t0, "")
            yield (variant, launch_index, *here, "warp", "end", w["endTs"] - t0, "")
        for m in launch["markers"]:
            yield (
                variant,
                launch_index,
                *where(m["locIdx"]),
                names[m["markerNameIdx"]],
                "mark",
                m["timestamp"] - t0,
                m.get("payloadVal", ""),
            )
        for r in launch["ranges"]:
            name = names[r["rangeNameIdx"]]
            locs = r["warpLocIdxs"]
            inner = r.get("internalEvents", [])
            start_payload = inner[0].get("payloadVal", "") if inner else ""
            end_payload = inner[-1].get("payloadVal", "") if inner else ""
            yield (variant, launch_index, *where(locs[0]), name, "start", r["startTs"] - t0, start_payload)
            yield (variant, launch_index, *where(locs[-1]), name, "end", r["endTs"] - t0, end_payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("trace", help="IKET JSON trace (iket_pid_<pid>.trace.json)")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--roles", default="")
    parser.add_argument("--launches", type=int, nargs="+", default=[-1])
    parser.add_argument("--out", required=True, help="output CSV, gzipped if it ends in .gz")
    args = parser.parse_args()

    with open(args.trace) as f:
        trace = json.load(f)
    opener = gzip.open if args.out.endswith(".gz") else open
    n = 0
    with opener(args.out, "wt", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for row in iket_rows(trace, args.launches, args.variant, parse_roles(args.roles)):
            writer.writerow(row)
            n += 1
    print(f"{args.out}: {n} events from {len(iket_launches(trace))} launches in the trace", file=sys.stderr)


if __name__ == "__main__":
    main()
