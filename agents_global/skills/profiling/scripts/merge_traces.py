"""Merge torch.profiler chrome traces into one file for side-by-side viewing in Perfetto, aligned at an anchor.

Each input's timestamps are shifted so its anchor lands at t = 0. Its CPU and GPU processes get small pids
and names like "<label> | GPU 0"; all GPU rows sort above all CPU rows, arms in input order, so the arms'
GPU streams sit next to each other. Profiler pseudo-processes (overhead, Spans) are dropped.

GPU-side `record_function` projections (`gpu_user_annotation`) often straddle kernel boundaries, which breaks
slice nesting on the kernel's stream track, so Perfetto hides them. They are moved to their own tracks in the
same GPU process: step markers (default `forward`, `backward`) go on a "step markers" thread track, and all
other annotations on one "stream N annotations" thread track per originating stream, sorted directly above
that stream's kernel track so each annotation sits next to the kernels it describes.

Perfetto's JSON importer silently drops events with negative timestamps, so after aligning every arm at its
anchor, all arms are shifted by one common offset that puts the earliest event at t = 0. Arms stay aligned
with each other; the anchor lands at the printed offset instead of 0. (Plain-`id` async events would also
be global, grouped by name across processes, which is why markers use a thread track.) torch projects `backward` onto the GPU with
zero duration (autograd launches from its own thread), so an empty GPU marker is extended to the last kernel
end in that GPU process.

The anchor is the Nth event (0-based, negative counts from the end) whose name equals the anchor name;
prefix it with `kernel:` to count only GPU kernels.

Usage: python3 merge_traces.py <out.json.gz> --anchor <name> [--anchor-index N] --trace "<label>=<trace.json.gz>" ...
  e.g. `--anchor forward --anchor-index -2` (last SFT step start), or `--anchor kernel:main_kernel --anchor-index 2`.
"""

import argparse
import gzip
import json

STEP_MARKERS = {"forward", "backward"}
ANNOTATION_TID_BASE, STEP_MARKER_TID = 800_000_000, 1

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("out", help="merged output path (.json.gz)")
parser.add_argument("--anchor", required=True, help="event name to align arms on; `kernel:` prefix counts only kernels")
parser.add_argument("--anchor-index", type=int, default=0, help="which occurrence of the anchor (negative counts from the end)")
parser.add_argument("--trace", action="append", required=True, help="LABEL=PATH, in arm order")
args = parser.parse_args()
out, anchor, nth = args.out, args.anchor, args.anchor_index
kernel_only = anchor.startswith("kernel:")
anchor_name = anchor.removeprefix("kernel:")
merged = []
for arm, spec in enumerate(args.trace):
    label, path = spec.split("=", 1)
    events = json.load(gzip.open(path))["traceEvents"]
    t0 = sorted(
        e["ts"]
        for e in events
        if e.get("ph") == "X" and e.get("name") == anchor_name and (not kernel_only or e.get("cat") == "kernel")
    )[nth]
    device_labels = {
        e["pid"]: e["args"]["labels"]
        for e in events
        if e.get("ph") == "M" and e.get("name") == "process_labels" and "labels" in e.get("args", {})
    }
    active = {e["pid"] for e in events if "pid" in e and e.get("ph") != "M"}
    new_pid, sort_index, annotation_tracks = {}, {}, {}
    step_markers, last_kernel_end, step_marker_pids = [], {}, set()
    for old, device in device_labels.items():
        if old not in active:
            continue
        is_gpu = device.startswith("GPU")
        index = int(device.split()[-1]) if is_gpu else 0
        new_pid[old] = (arm + 1) * 100 + (1 + index if is_gpu else 0)
        sort_index[old] = (0 if is_gpu else 1_000_000) + arm * 1000 + index
    for e in events:
        if e.get("pid") not in new_pid:
            continue
        old = e["pid"]
        if e.get("ph") == "M" and e.get("name") in ("process_name", "process_labels", "process_sort_index"):
            continue
        if e.get("ph") == "M" and e.get("name") == "thread_sort_index" and device_labels[old].startswith("GPU"):
            continue
        e = dict(e, pid=new_pid[old])
        if "ts" in e:
            e["ts"] = e["ts"] - t0
        if e.get("cat") == "gpu_user_annotation" and e.get("name") in STEP_MARKERS:
            step_markers.append(e)
            continue
        if e.get("cat") == "kernel":
            last_kernel_end[e["pid"]] = max(last_kernel_end.get(e["pid"], e["ts"]), e["ts"] + e["dur"])
        if e.get("cat") == "gpu_user_annotation":
            stream = e.get("tid")
            e["tid"] = ANNOTATION_TID_BASE + int(stream)
            annotation_tracks.setdefault(e["pid"], set()).add((e["tid"], stream))
        merged.append(e)
    for e in step_markers:
        end = e["ts"] + e.get("dur", 0)
        if end - e["ts"] < 1000.0:
            end = last_kernel_end.get(e["pid"], end)
        merged.append({"ph": "X", "cat": "step", "name": e["name"], "pid": e["pid"], "tid": STEP_MARKER_TID, "ts": e["ts"], "dur": end - e["ts"]})
        step_marker_pids.add(e["pid"])
    for pid in step_marker_pids:
        merged.append({"ph": "M", "name": "thread_name", "pid": pid, "tid": STEP_MARKER_TID, "args": {"name": "step markers"}})
        merged.append({"ph": "M", "name": "thread_sort_index", "pid": pid, "tid": STEP_MARKER_TID, "args": {"sort_index": -1}})
    streams_by_pid = {}
    for e in merged:
        if e.get("cat") == "kernel" and e["pid"] in {new_pid[o] for o in new_pid if device_labels[o].startswith("GPU")}:
            streams_by_pid.setdefault(e["pid"], set()).add(e["tid"])
    for pid, tracks in annotation_tracks.items():
        streams_by_pid.setdefault(pid, set()).update(stream for _, stream in tracks)
    for pid, streams in streams_by_pid.items():
        for rank, stream in enumerate(sorted(streams, key=int)):
            annotation_tid = ANNOTATION_TID_BASE + int(stream)
            merged.append({"ph": "M", "name": "thread_sort_index", "pid": pid, "tid": annotation_tid, "args": {"sort_index": 2 * rank}})
            merged.append({"ph": "M", "name": "thread_sort_index", "pid": pid, "tid": stream, "args": {"sort_index": 2 * rank + 1}})
    for pid, tracks in annotation_tracks.items():
        for tid, stream in tracks:
            merged.append({"ph": "M", "name": "thread_name", "pid": pid, "tid": tid, "args": {"name": f"stream {stream} annotations"}})
    for old, pid in new_pid.items():
        merged.append({"ph": "M", "name": "process_name", "pid": pid, "args": {"name": f"{label} | {device_labels[old]}"}})
        merged.append({"ph": "M", "name": "process_sort_index", "pid": pid, "args": {"sort_index": sort_index[old]}})
for e in merged:
    if e.get("ph") == "M":
        e.pop("ts", None)
offset = -min((e["ts"] for e in merged if "ts" in e), default=0.0)
offset = max(offset, 0.0)
for e in merged:
    if "ts" in e:
        e["ts"] += offset
print(f"anchor at t = {offset / 1e3:.3f} ms in every arm")
with gzip.open(out, "wt") as f:
    json.dump({"traceEvents": merged, "displayTimeUnit": "ms"}, f)
print(f"{out}: {len(merged)} events")
