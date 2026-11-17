# /// script
# requires-python = ">=3.10"
# ///
"""Host-blocking CUDA calls and pageable or synchronous copies per process from an nsys SQLite export.

The nsys counterpart of `find_syncs.py` for captures that cover a known number of steps (e.g. a
`--capture-range=cudaProfilerApi` capture started and stopped by `sync_stacks/sitecustomize.py`'s
SYNC_STACKS_PROFILER_STEPS). It sees what torch's sync debug mode misses (NCCL, ctypes or driver launches, library
host code), but no Python lines. Each process is labeled by the CUDA device its kernels ran on.

Per process it counts, divided by `--steps`:
- blocking runtime and driver calls (`cudaStreamSynchronize`, `cudaDeviceSynchronize`, `cudaEventSynchronize`,
  synchronous `cudaMemcpy*`, `cudaMemset`, their `cu*` equivalents), with the host time spent in them;
- `cudaMemcpy*Async` calls whose copy touched pageable host memory (host-blocking for a device-to-host copy, staged
  through a driver buffer for host-to-device), by direction and memory kinds;
- with `--all-copies`, every host-device copy by direction and memory kinds (pinned ones included);
- rows of `CUPTI_ACTIVITY_KIND_SYNCHRONIZATION` (present when nsys traced CUDA synchronization), by type and the API
  call they came from (its correlation id; "?" when the call is not in the export), except
  `--skip-sync-types` (default: stream wait, a device-side wait); their host ms is the GPU-side span, not host time.

Export first: `nsys export --type sqlite --force-overwrite true -o out.sqlite out.nsys-rep`.

Usage: uv run --script nsys_syncs.py out.sqlite [--steps 3] [--all-copies] [--device 0] [--list-threads]
"""

import argparse
import sqlite3
from collections import defaultdict

BLOCKING = {
    "cudaStreamSynchronize", "cudaDeviceSynchronize", "cudaEventSynchronize", "cudaThreadSynchronize",
    "cudaMemcpy", "cudaMemcpy2D", "cudaMemcpy3D", "cudaMemcpyFromSymbol", "cudaMemcpyToSymbol", "cudaMemset",
    "cuStreamSynchronize", "cuCtxSynchronize", "cuEventSynchronize", "cuMemcpy", "cuMemcpyDtoH", "cuMemcpyHtoD",
    "cuMemcpyDtoD", "cuMemcpyAtoH",
}


def base_name(name):
    name = name.split("(")[0]
    for suffix in ("_v2", "_v3", "_ptsz", "_ptds", "_v7000", "_v3020"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def enum(db, table):
    if table not in tables(db):
        return {}
    return {row[0]: row[-1] for row in db.execute(f"SELECT * FROM {table}")}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sqlite")
    parser.add_argument("--steps", type=float, default=1.0, help="steps the capture covers; counts are divided by it")
    parser.add_argument("--device", type=int, default=None, help="only the process whose kernels ran on this device")
    parser.add_argument("--all-copies", action="store_true", help="also list pinned and device-only copies")
    parser.add_argument("--skip-sync-types", default="Stream wait")
    parser.add_argument("--list-threads", action="store_true", help="split every row by host thread id")
    args = parser.parse_args()

    db = sqlite3.connect(args.sqlite)
    have = tables(db)
    names = dict(db.execute("SELECT id, value FROM StringIds"))

    devices = defaultdict(set)
    for pid, device in db.execute("SELECT DISTINCT globalPid / 16777216 % 16777216, deviceId FROM CUPTI_ACTIVITY_KIND_KERNEL"):
        devices[pid].add(device)

    def label(pid):
        return ",".join(f"dev{d}" for d in sorted(devices.get(pid, ()))) or "nodev"

    def wanted(pid):
        return args.device is None or args.device in devices.get(pid, ())

    copies = {}
    if "CUPTI_ACTIVITY_KIND_MEMCPY" in have:
        kinds = enum(db, "ENUM_CUDA_MEM_KIND")
        opers = enum(db, "ENUM_CUDA_MEMCPY_OPER")
        for corr, pid, oper, src, dst, size in db.execute(
            "SELECT correlationId, globalPid / 16777216 % 16777216, copyKind, srcKind, dstKind, bytes "
            "FROM CUPTI_ACTIVITY_KIND_MEMCPY"
        ):
            copies[(pid, corr)] = (
                opers.get(oper, str(oper)), kinds.get(src, str(src)), kinds.get(dst, str(dst)), size
            )

    rows = defaultdict(lambda: [0, 0.0, 0])
    calls = {}
    for table in ("CUPTI_ACTIVITY_KIND_RUNTIME", "CUDA_DRIVER_API" if "CUDA_DRIVER_API" in have else None):
        if table is None or table not in have:
            continue
        for start, end, name_id, gtid, corr in db.execute(
            f"SELECT start, end, nameId, globalTid, correlationId FROM {table}"
        ):
            pid, tid = gtid // 16777216 % 16777216, gtid % 16777216
            if not wanted(pid):
                continue
            name = base_name(names.get(name_id, str(name_id)))
            calls[(pid, corr)] = (name, tid)
            copy = copies.get((pid, corr))
            key = None
            if name in BLOCKING:
                key = ("blocking", name, "" if copy is None else f"{copy[0]} {copy[1]}->{copy[2]}")
            elif copy is not None and "Memcpy" in name:
                touches_pageable = "Pageable" in copy[1] or "Pageable" in copy[2]
                if touches_pageable or (args.all_copies and copy[0] != "Device-to-Device"):
                    key = ("pageable" if touches_pageable else "copy", name, f"{copy[0]} {copy[1]}->{copy[2]}")
            if key is None:
                continue
            key = (label(pid), *(key + ((tid,) if args.list_threads else ())))
            row = rows[key]
            row[0] += 1
            row[1] += (end - start) / 1e6
            row[2] += copy[3] if copy is not None else 0

    if "CUPTI_ACTIVITY_KIND_SYNCHRONIZATION" in have:
        sync_types = enum(db, "ENUM_CUPTI_SYNC_TYPE")
        skip = {s.strip() for s in args.skip_sync_types.split(",") if s.strip()}
        for start, end, sync_type, gpid, corr in db.execute(
            "SELECT start, end, syncType, globalPid, correlationId FROM CUPTI_ACTIVITY_KIND_SYNCHRONIZATION"
        ):
            pid = gpid // 16777216 % 16777216
            name = sync_types.get(sync_type, str(sync_type))
            if not wanted(pid) or any(s.lower() in name.lower() for s in skip):
                continue
            call, tid = calls.get((pid, corr), ("?", "-"))
            key = (label(pid), "sync-activity", name, f"via {call}", *((tid,) if args.list_threads else ()))
            row = rows[key]
            row[0] += 1
            row[1] += (end - start) / 1e6

    header = ["process", "class", "call", "copy"] + (["tid"] if args.list_threads else [])
    print("| " + " | ".join(header + ["per step", "host ms per step", "bytes per step"]) + " |")
    print("|" + "---|" * (len(header) + 3))
    for key in sorted(rows):
        count, ms, size = rows[key]
        cells = [str(k) for k in key] + [f"{count / args.steps:g}", f"{ms / args.steps:.3f}", f"{size / args.steps:.0f}"]
        print("| " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
