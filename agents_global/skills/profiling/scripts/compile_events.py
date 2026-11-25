# /// script
# requires-python = ">=3.10"
# ///
"""Place every rank's torch.compile recompiles and every node's JIT kernel compiles in the training step they stalled.

Paths are relative to RUN_DIR unless absolute. The defaults match a prime-rl run directory, and
`projects/<repo>.md` lists the flags a repo's runs need.
- Steps: `--metrics` (default `monitors/file/metrics.jsonl`) holds JSON lines. Each record carrying `--step-key`
  (default `step`), `--duration-key` (default `time/step`) and `--end-key` (default `time`, the step's end in epoch
  seconds) defines one step, so step k spans (end of step k-1, end of step k]. `--row-filter KEY=VALUE` (repeatable)
  keeps only matching records, for logs where several processes write the same keys under one step index.
- Dynamo: every `Recompiling function` record in the `*.log` files under `--dynamo-logs` (default
  `logs/attempt_<attempt>/trainer`), written with `TORCH_LOGS=recompiles`. The rank comes from torch's `[rankR]:`
  prefix and the time from the glog timestamp (`V1019 19:49:02.48`, local time; the year is taken from the first step).
- JIT caches: `<kind>_cache_<host>.txt` files anywhere under `--listings` (default `logs/attempt_<attempt>`), one line
  per cache file, `<mtime epoch seconds> <path>`, written after training. Each entry's mtime is when that node first
  compiled it, and `<kind>` names the column. Point each cache at a fresh per-run directory, or entries from earlier
  runs land in the listing (or pass `--start`). Files count by entry: in the directory caches (`triton`, `deep_gemm`,
  `torch_extensions`, `tilelang`) one per directory, at its first file's mtime; in the others one per directory and
  file name up to the first dot (one cache key's files). Listings of every cache the prime-rl trainer sets (its
  `utils/process.py`), run on each node after training:
    find $TRITON_CACHE_DIR -mindepth 2 -maxdepth 2 -name "*.cubin" -printf "%T@ %f\n" > triton_cache_$(hostname).txt
    find $DG_JIT_CACHE_DIR/cache -mindepth 1 -maxdepth 1 -printf "%T@ %f\n" > deep_gemm_cache_$(hostname).txt
    for kind in inductor:TORCHINDUCTOR_CACHE_DIR quack:QUACK_CACHE_DIR cute_dsl:CUTE_DSL_CACHE_DIR \
        torch_extensions:TORCH_EXTENSIONS_DIR kda_cuda:PRIME_RL_KERNEL_CACHE tilelang:TILELANG_CACHE_DIR; do
      dir=$(printenv ${kind#*:}) && [ -d "$dir" ] && (cd "$dir" && find . -type f -printf "%T@ %P\n") \
        > ${kind%%:*}_cache_$(hostname).txt
    done
  Triton writes one `<hash>/<kernel>.cubin` per specialization, so the Triton listing catches hand-written kernels
  that Dynamo never logs, e.g. a second variant compiled when an int argument first becomes divisible by 16. It
  also holds Inductor's generated kernels (`triton_poi_*`, `triton_red_*`, ...), which first compile in step 1.
  The inductor listing adds Inductor's FX graph, AOTAutograd and autotune result files; quack's holds its kernels and
  `*.autotune.json` results; cute_dsl, torch_extensions, kda_cuda (prime-rl's KDA CUDA kernels) and tilelang hold
  those JIT builds.
  `--deepgemm-listing FILE[:HOST]` (repeatable) replaces the DeepGEMM listings found under `--listings`, e.g. for
  runs launched outside the `rl` launcher. A listing may also use
  `find <cache> -type f -printf "%TY-%Tm-%Td %TT %p\n"` lines; each `kernel.*` entry counts once, at its first file's
  mtime.
- Compile cache bundles: `--bundle TAR[:HOST]` (repeatable) reads the members of a prime-rl compile cache bundle
  (`model.compile_cache_bundle_dir`, a gzipped tar of `<VARIABLE>/<path in that cache>` files that keep their
  mtimes) as listings, each cache by its variable: TORCHINDUCTOR_CACHE_DIR inductor, TRITON_CACHE_DIR triton,
  DG_JIT_CACHE_DIR deep_gemm, QUACK_CACHE_DIR quack, CUTE_DSL_CACHE_DIR cute_dsl, TORCH_EXTENSIONS_DIR
  torch_extensions, PRIME_RL_KERNEL_CACHE kda_cuda, TILELANG_CACHE_DIR tilelang. HOST defaults to `node<k>` for a
  `-node<k>.tar.gz` bundle and to `shared` for the shared one (written by node 0). A node's bundle holds only the
  files the shared one lacks, so attribution to hosts is partial. A bundle a warm run rewrote also holds the files of
  the runs before it: pass `--start` to set those apart. Reading a bundle decompresses all of it (hundreds of MB to
  GB): run on a compute node.
- `--start EPOCH` (the run's job start, e.g. from `sacct -o Start`): entries older than it go to a `before` row and
  entries newer than the last step's end to an `after` row, and neither counts toward the last compile step. Without
  it, every entry lands in the step whose window holds it, the first or the last step at the ends.

Prints a markdown table per step with any event (step time, Dynamo recompiles with their ranks, compiles per JIT cache
with their nodes), then `last compile step: K` over all events. Pass K + 1 as the start of `run_metrics.py --steady` to
report steady-state step time after every compile. `--events-csv` writes one row per event: kind, step, time, where
(rank or host), what (function and first guard failure, or cache entry).

Usage:
  uv run --script compile_events.py <run dir>
  uv run --script compile_events.py <run dir> --attempt 1 --events-csv events.csv
  uv run --script compile_events.py <run dir> --metrics metrics.jsonl --duration-key step_seconds \\
    --end-key wall_time --dynamo-logs logs --listings caches --row-filter role=trainer
  uv run --script compile_events.py <run dir> --dynamo-logs torchrun --deepgemm-listing listing.txt:node0
  uv run --script compile_events.py <warm run dir> --bundle <cold run dir>/bundles/<key>.tar.gz --start 1764027747
"""

import argparse
import csv
import json
import os
import re
import tarfile
import time
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

RECOMPILE = re.compile(r"\[rank(\d+)\]:[VIWE](\d{4}) (\d\d:\d\d:\d\d\.\d+) .*\[__recompiles\] Recompiling function (\S+)")
REASON = re.compile(r"\[__recompiles\]\s+- \d+/\d+: (.*)")
DIRECTORY_KINDS = ("triton", "deep_gemm", "torch_extensions", "tilelang")
BUNDLE_KINDS = {
    "TORCHINDUCTOR_CACHE_DIR": "inductor",
    "TRITON_CACHE_DIR": "triton",
    "DG_JIT_CACHE_DIR": "deep_gemm",
    "QUACK_CACHE_DIR": "quack",
    "CUTE_DSL_CACHE_DIR": "cute_dsl",
    "TORCH_EXTENSIONS_DIR": "torch_extensions",
    "PRIME_RL_KERNEL_CACHE": "kda_cuda",
    "TILELANG_CACHE_DIR": "tilelang",
}
BEFORE, AFTER = -1, float("inf")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--attempt", type=int, default=1, help="fills <attempt> in the default log paths")
    parser.add_argument("--metrics", type=Path, default=Path("monitors/file/metrics.jsonl"))
    parser.add_argument("--step-key", default="step")
    parser.add_argument("--duration-key", default="time/step")
    parser.add_argument("--end-key", default="time", help="the step's end time in epoch seconds")
    parser.add_argument("--row-filter", action="append", default=[], metavar="KEY=VALUE",
                        help="keep only metrics records whose KEY equals VALUE (repeatable)")
    parser.add_argument("--dynamo-logs", type=Path, default=None, help="default logs/attempt_<attempt>/trainer")
    parser.add_argument("--listings", type=Path, default=None, help="default logs/attempt_<attempt>")
    parser.add_argument("--deepgemm-listing", action="append", default=[], metavar="FILE[:HOST]",
                        help="extra DeepGEMM cache listing; replaces the deep_gemm_cache_<host>.txt search when given")
    parser.add_argument("--bundle", action="append", default=[], metavar="TAR[:HOST]",
                        help="a compile cache bundle whose members count as listings of their caches (repeatable)")
    parser.add_argument("--start", type=float, default=None,
                        help="the run's start in epoch seconds: older entries and ones after the last step go apart")
    parser.add_argument("--events-csv", type=Path, default=None)
    args = parser.parse_args()
    args.row_filter = [tuple(spec.split("=", 1)) for spec in args.row_filter]
    return args


def load_steps(path: Path, step_key: str, end_key: str, duration_key: str,
               row_filters: list[tuple[str, str]]) -> list[tuple[int, float, float]]:
    """(step, end epoch seconds, step seconds), sorted by step, from the records passing every row filter."""
    steps = {}
    for line in path.open():
        record = json.loads(line)
        if duration_key in record and all(str(record.get(key)) == value for key, value in row_filters):
            steps[record[step_key]] = (record[end_key], record[duration_key])
    return [(step, end, seconds) for step, (end, seconds) in sorted(steps.items())]


def glog_epoch(mmdd: str, clock: str, year: int) -> float:
    whole, _, fraction = clock.partition(".")
    struct = time.strptime(f"{year}{mmdd} {whole}", "%Y%m%d %H:%M:%S")
    return time.mktime(struct) + float(f"0.{fraction}")


def dynamo_events(log_dir: Path, year: int) -> list[tuple[float, str, str]]:
    """(epoch seconds, rank, function: first guard failure) per recompile, deduplicated across tee'd copies."""
    events = set()
    for log in sorted(log_dir.rglob("*.log")):
        pending = None
        for line in log.open(errors="replace"):
            if match := RECOMPILE.search(line):
                pending = (glog_epoch(match.group(2), match.group(3), year), f"rank{match.group(1)}", match.group(4))
            elif pending and (match := REASON.search(line)):
                events.add((pending[0], pending[1], f"{pending[2]}: {match.group(1).split('  #')[0].strip()}"))
                pending = None
    return sorted(events)


def cache_entry(kind: str, path: str) -> str | None:
    """The cache entry a file belongs to: its directory in the directory caches, else its directory and name up to the
    first dot; DeepGEMM's is the `kernel.*` part of the path (None without one). A bare file name is its own entry."""
    if kind == "deep_gemm":
        return next((part for part in Path(path).parts if part.startswith("kernel.")), None)
    directory, name = os.path.split(path)
    if not directory:
        return path
    return directory if kind in DIRECTORY_KINDS else os.path.join(directory, name.split(".")[0])


def first_per_entry(kind: str, files: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """(earliest mtime, entry) per cache entry of the (mtime, path) ``files``; every bare file name counts."""
    first, bare = {}, []
    for epoch, path in files:
        entry = cache_entry(kind, path)
        if entry is None:
            continue
        if "/" not in path and kind != "deep_gemm":
            bare.append((epoch, path))
        else:
            first[entry] = min(epoch, first.get(entry, epoch))
    return bare + [(epoch, entry) for entry, epoch in first.items()]


def listing_entries(listing: Path, kind: str) -> list[tuple[float, str]]:
    """(mtime epoch seconds, entry) from `<epoch> <path>` or `<YYYY-MM-DD> <HH:MM:SS.frac> <path>` lines."""
    files = []
    for line in listing.open():
        fields = line.split()
        if len(fields) >= 3 and re.fullmatch(r"\d{4}-\d\d-\d\d", fields[0]):
            whole, _, fraction = fields[1].partition(".")
            epoch = time.mktime(time.strptime(f"{fields[0]} {whole}", "%Y-%m-%d %H:%M:%S")) + float(f"0.{fraction or 0}")
            path = fields[2]
        elif len(fields) == 2:
            epoch, path = float(fields[0]), fields[1]
        else:
            continue
        files.append((epoch, path))
    return first_per_entry(kind, files)


def bundle_events(spec: str) -> list[tuple[str, float, str, str]]:
    """(kind, mtime epoch seconds, host, entry) per cache entry of the compile cache bundle ``spec`` (TAR[:HOST])."""
    path, _, host = spec.partition(":")
    if not host:
        node = re.search(r"-node(\d+)\.tar\.gz$", path)
        host = f"node{node.group(1)}" if node else "shared"
    files = defaultdict(list)
    with tarfile.open(path) as tar:
        for member in tar:
            variable, _, relative = member.name.removeprefix("./").partition("/")
            if member.isfile() and variable in BUNDLE_KINDS:
                files[BUNDLE_KINDS[variable]].append((member.mtime, relative))
    return [(kind, epoch, host, entry) for kind, kind_files in files.items()
            for epoch, entry in first_per_entry(kind, kind_files)]


def cache_events(listings: list[tuple[Path, str, str]]) -> list[tuple[str, float, str, str]]:
    """(kind, mtime epoch seconds, host, entry) per entry of every (listing, kind, host)."""
    events = []
    for listing, kind, host in listings:
        events += [(kind, epoch, host, entry) for epoch, entry in listing_entries(listing, kind)]
    return sorted(events)


def main():
    args = parse_args()
    steps = load_steps(args.run_dir / args.metrics, args.step_key, args.end_key, args.duration_key, args.row_filter)
    ends = [end for _, end, _ in steps]
    year = time.localtime(ends[0]).tm_year
    attempt_dir = Path("logs") / f"attempt_{args.attempt}"
    dynamo_dir = args.run_dir / (args.dynamo_logs or attempt_dir / "trainer")
    listings_dir = args.run_dir / (args.listings or attempt_dir)

    def step_of(epoch: float) -> float:
        if args.start is not None and epoch < args.start:
            return BEFORE
        if args.start is not None and epoch > ends[-1]:
            return AFTER
        return steps[min(bisect_left(ends, epoch), len(steps) - 1)][0]

    listings = []
    for path in sorted(listings_dir.rglob("*_cache_*.txt")):
        kind, _, host = path.stem.rpartition("_cache_")
        if not (args.deepgemm_listing and kind == "deep_gemm"):
            listings.append((path, kind, host))
    for spec in args.deepgemm_listing:
        path, _, host = spec.partition(":")
        listings.append((args.run_dir / path, "deep_gemm", host or "node"))
    events = [("dynamo", *e) for e in dynamo_events(dynamo_dir, year)]
    if not events:
        print(f"note: no `Recompiling function` records under {dynamo_dir} (logs missing, or not run with "
              "TORCH_LOGS=recompiles); Dynamo counts below are not evidence of zero recompiles.\n")
    if not listings and not args.bundle:
        print("note: no JIT cache listing found; the missing compile columns are not evidence of zero compiles.\n")
    events += cache_events(listings)
    for spec in args.bundle:
        events += bundle_events(spec)
    cache_kinds = sorted({kind for kind, *_ in events} - {"dynamo"})
    by_step: dict[float, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    rows = []
    for kind, epoch, where, what in events:
        step = step_of(epoch)
        by_step[step][kind].append(where)
        rows.append((kind, step, f"{epoch:.3f}", where, what))

    seconds = {step: f"{s:.2f}" for step, _, s in steps}
    labels = {BEFORE: "before", AFTER: "after"}
    cache_headers = "".join(f" {kind} compiles | nodes |" for kind in cache_kinds)
    print("| step | step time (s) | Dynamo recompiles | ranks |" + cache_headers)
    print("|---:|---:|---:|---|" + "---:|---|" * len(cache_kinds))
    for step in sorted(by_step):
        dynamo = by_step[step]["dynamo"]
        ranks = ",".join(sorted(set(dynamo), key=lambda r: int(r[4:])))
        cells = "".join(f" {len(by_step[step][k])} | {','.join(sorted(set(by_step[step][k])))} |" for k in cache_kinds)
        print(f"| {labels.get(step, step)} | {seconds.get(step, '')} | {len(dynamo)} | {ranks} |{cells}")
    totals = [f"{sum(k == 'dynamo' for k, *_ in rows)} Dynamo recompiles"]
    totals += [f"{sum(k == kind for k, *_ in rows)} {kind} compiles" for kind in cache_kinds]
    print(f"\n{len(steps)} steps, " + ", ".join(totals))
    in_run = [step for step in by_step if step not in labels]
    print(f"last compile step: {max(in_run) if in_run else 0}")

    if args.events_csv:
        with args.events_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["kind", "step", "epoch", "where", "what"])
            writer.writerows((kind, labels.get(step, step), *rest) for kind, step, *rest in
                             sorted(rows, key=lambda r: (r[1], r[0], r[3])))


if __name__ == "__main__":
    main()
