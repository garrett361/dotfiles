"""Rank a kernel's source lines (or SASS instructions) by warp-stall samples from an ncu report.

Runs `ncu --import <report> --page source --print-source cuda,sass --csv` and prints a markdown table
of the hottest high-level source lines: warp-stall samples, their share of the kernel's samples,
instructions executed, and the dominant stall reasons. The "source" is whatever the kernel's line
info points at: `.cu` files for CUDA C++, the Python file for CuTe DSL kernels compiled with
`CUTE_DSL_LINEINFO=1`, Triton's `.py` for Triton kernels.

The report must carry source counters: collect with `--section SourceCounters` (or `--set full`)
and `--import-source yes`, on a kernel built with line info. Without line info the source page has
no line rows, and only `--view sass` works. If the source file was a temporary that no longer exists
(TileLang compiles from `/tmp/tmp*/tvm_kernels.cu`), pass a saved copy with `--resolve-source-file`.

Usage:
  python3 ncu_source_lines.py report.ncu-rep --top 15
  python3 ncu_source_lines.py report.ncu-rep --kernel regex:my_kernel --view sass --top 30
  python3 ncu_source_lines.py report.ncu-rep --resolve-source-file /path/to/device_kernel_copy.cu
"""

import argparse
import csv
import io
import re
import subprocess
from collections import defaultdict

ALL_SAMPLES = "Warp Stall Sampling (All Samples)"
INST_EXECUTED = "Instructions Executed"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report")
    parser.add_argument("--ncu", default="/usr/local/cuda-13.0/bin/ncu", help="ncu binary")
    parser.add_argument("--kernel", default=None, help="passed to ncu --kernel-name, e.g. regex:attn")
    parser.add_argument("--view", choices=("line", "sass"), default="line", help="rank source lines or SASS")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--stalls", type=int, default=3, help="stall reasons listed per row")
    parser.add_argument("--source-width", type=int, default=70)
    parser.add_argument(
        "--resolve-source-file", default=None, help="passed to ncu: comma-separated files to resolve sources against"
    )
    return parser.parse_args()


def read_source_csv(args):
    command = [args.ncu, "--import", args.report, "--page", "source", "--print-source", "cuda,sass", "--csv"]
    if args.kernel:
        command += ["--kernel-name", args.kernel]
    if args.resolve_source_file:
        command += ["--resolve-source-file", args.resolve_source_file]
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


def to_number(value):
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_rows(text):
    """Yield (launch, file, line_no, source, kind, metrics) per row; kind is "line" or "sass"."""
    file_path, launch, header = "", "", None
    files_seen, launches = defaultdict(set), defaultdict(int)
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if row[0] == "File Path":
            file_path = row[1]
        elif row[0] == "Function Name":
            function = row[1]
            if file_path in files_seen[function]:
                files_seen[function] = set()
                launches[function] += 1
            files_seen[function].add(file_path)
            launch = function if launches[function] == 0 else f"{function} #{launches[function] + 1}"
        elif row[0] == "Line No":
            header = row
        elif header is not None:
            metrics = {name: to_number(value) for name, value in zip(header[4:], row[4:])}
            if row[0]:
                yield launch, file_path, row[0], row[1].strip(), "line", metrics
            else:
                yield launch, file_path, row[2], row[3].strip(), "sass", metrics


def stall_summary(metrics, count):
    stalls = {
        name.removeprefix("stall_"): value
        for name, value in metrics.items()
        if name.startswith("stall_") and "(Not Issued)" not in name and value > 0
    }
    ranked = sorted(stalls.items(), key=lambda item: -item[1])[:count]
    return ", ".join(f"{name} {int(value)}" for name, value in ranked)


def main():
    args = parse_args()
    rows = [row for row in parse_rows(read_source_csv(args)) if row[4] == args.view]
    if not rows:
        raise SystemExit(f"no {args.view} rows in the source page; was the kernel built with line info?")
    total_samples = defaultdict(float)
    for launch, _, _, _, _, metrics in rows:
        total_samples[launch] += metrics.get(ALL_SAMPLES, 0.0)
    rows.sort(key=lambda row: -row[5].get(ALL_SAMPLES, 0.0))
    location_header = "file:line" if args.view == "line" else "address"
    print(f"| kernel | {location_header} | source | samples | % of kernel | inst executed | top stalls |")
    print("|---|---|---|---:|---:|---:|---|")
    for launch, file_path, location, source, _, metrics in rows[: args.top]:
        samples = metrics.get(ALL_SAMPLES, 0.0)
        share = 100.0 * samples / total_samples[launch] if total_samples[launch] else 0.0
        where = f"{file_path.rsplit('/', 1)[-1]}:{location}" if args.view == "line" else location
        text = re.sub(r"\s+", " ", source)[: args.source_width].replace("|", "\\|")
        print(
            f"| {launch[:40]} | {where} | `{text}` | {int(samples)} | {share:.1f} | "
            f"{int(metrics.get(INST_EXECUTED, 0.0))} | {stall_summary(metrics, args.stalls)} |"
        )


if __name__ == "__main__":
    main()
