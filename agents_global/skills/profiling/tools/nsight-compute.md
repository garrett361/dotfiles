# Nsight Compute (ncu)

Status: checked on 2026-09-24 with ncu 2025.3.1 on a B300 SXM6 node (driver 580.173.02, CUDA 13.0).
Performance counters are blocked for non-admin users, so no kernel metrics have been collected yet.
Nothing under "Not yet verified" has produced a report on this cluster.
On the H200 nodes counters do work. See "Verified on H200 (sm90)" below.

## When to use

- Why a single kernel is slow: achieved bandwidth and FLOPs against peak, occupancy, stalls, cache behavior.
- Comparing one kernel's metrics before and after a change.
- Op-level scripts only. Replay-based measurement makes whole training runs impractical.

## Verified recipes

- Binaries: `ncu` on `PATH` is `/usr/local/cuda-12.9/bin/ncu`, a shell wrapper (as is
  `/usr/local/cuda-13.0/bin/ncu`) that runs the newest install under `/opt/nvidia/nsight-compute/`
  (2025.2.1 and 2025.3.1 exist; both wrappers report 2025.3.1). Same layout on login and compute nodes.
- GPU support: on a compute node, `ncu --query-metrics --devices 0` prints
  `Device NVIDIA B300 SXM6 PC (GB110)`, and `gb110` is in `ncu --list-chips`, so 2025.3.1 recognizes the
  chip. It then fails with the permission error below.
- Check counter permissions on a compute node before planning any ncu work:
  `grep RmProfilingAdminOnly /proc/driver/nvidia/params`. A value of `1` means only admins can profile.
- `ncu --list-sections` works without counters and lists the identifiers for `--section`
  (e.g. `SpeedOfLight`, `MemoryWorkloadAnalysis`, `SpeedOfLight_RooflineChart`, `Occupancy`).
- Run under Slurm on one GPU, wrapping `uv run` directly; ncu attaches to the Python child process:
  `srun -p all -N1 --gpus=1 --time=00:20:00 bash -lc 'ncu ... uv run python script.py'`.

## Verified on H200 (sm90), 2026-10-10

Counters work for normal users on the `prime-nebius-puku-h200-gpu-*` nodes (ncu 2025.3.1 via
`/usr/local/cuda-13.0/bin/ncu`, SLURM job 3569).

- One kernel, one launch, with per-line source counters:
  `ncu --target-processes all -k regex:<name> -s 1 -c 1 --section SpeedOfLight --section SourceCounters --section LaunchStats --import-source yes -o out -f uv run --no-sync python script.py`.
  `--target-processes all` is needed because `uv run` starts Python as a child. `-s 1` skipped the first
  matching launch and `-c 1` stopped after one. These three sections took 13 replay passes.
- Source correlation needs a kernel built with line info (CUDA `-lineinfo`, CuTe DSL `CUTE_DSL_LINEINFO=1`).
  `ncu -i out.ncu-rep --page source --print-source cuda,sass --csv` prints one row per source line
  (metrics summed over its instructions) followed by its SASS rows. `--print-source cuda` alone prints
  the file with no metric columns. `--import-source yes` embeds the source file in the report.
  Rank lines with `scripts/ncu_source_lines.py`.
- ncu locks clocks to base by default (`--clock-control base`): the report showed `SM Frequency 1.50 GHz`
  on an H200 whose maximum is 1.98 GHz. Kernel durations under ncu are longer than CUDA-event timings.
  Take timings from events, and the why from ncu.
- Launch Statistics "Registers Per Thread" is the allocated count: 16 for a kernel whose cubin says
  `REG:12` (`cuobjdump --dump-resource-usage`).
- Full set on a TileLang kernel at a production shape (DSv4 sparse attention forward):
  `ncu --target-processes all -k regex:^main_kernel$ -c 1 --set full --import-source yes -o out -f uv run --no-sync python bench.py ...`.
  - It took 38 replay passes on a kernel that ran 3.42 ms under ncu. The SM frequency showed 1.36 GHz in this
    collection.
  - ncu warned that 6 `ctc__*` metrics were unavailable. The rest of the report was complete.
  - The Memory Workload Analysis, Warp State Statistics and Occupancy sections print with
    `ncu -i out.ncu-rep --page details --section <id>`.
  - `SpeedOfLight_RooflineChart` prints "No metrics to show" as text; it is a chart for the GUI.
  - `ncu -i out.ncu-rep --page raw --csv` exports one row per kernel with every metric (2238 columns here).
- TileLang names every kernel `main_kernel`, forward and backward alike. Select by launch order, and confirm the
  pick from the grid in the report header (`main_kernel (8192, 1, 1)x(256, 1, 1)`: one block per query).
- TileLang always compiles with `-lineinfo`. The source it compiles is a temporary,
  `/tmp/tmp*/tvm_kernels.cu`, deleted after the build, so `--import-source yes` warns
  `Failed to import the following source files` and the report has no source text.
  - The same source is kept in TileLang's disk cache as
    `$TILELANG_CACHE_DIR/<version>/<platform>/kernels/<key>/device_kernel.cu`. The default cache dir is
    `~/.tilelang/cache`.
  - Find the entry by grepping the `device_kernel.cu` files for the kernel's parameter names. Copy it, then pass
    the copy to `ncu -i ... --resolve-source-file <copy>` or to
    `scripts/ncu_source_lines.py --resolve-source-file <copy>`.
  - With that, lines resolve to the generated CUDA: the hottest stall line was the guarded KV gather
    `tl::cp_async_gs_conditional<16>(...)`. CuTe headers (`intrin.h`, `common.h`) resolve without help.

## Gotchas

- `ERR_NVGPUCTRPERM` on every collection: the driver has `RmProfilingAdminOnly: 1`. The fix is admin-side:
  set the `nvidia` module option `NVreg_RestrictProfilingToAdminUsers=0` (modprobe config, then reload the
  module or reboot), or grant sudo for `ncu`. Until then, use `torch.profiler` or `do_bench`.
- On the permission error the target still runs to completion, but ncu exits with code 1, so the script's
  own success output does not mean profiling worked.
- `--launch-skip` counts only launches that match the `--kernel-name` filter;
  `--launch-skip-before-match` counts all launches (from `ncu --help`).

## Not yet verified

These flags exist in `ncu --help` for 2025.3.1, but none has produced a report on any node yet. (B300 is
blocked on counter permissions. H200 works, and its verified items are listed above.)
- `--print-summary`.
- NVTX filtering with `--nvtx --nvtx-include`. Per `ncu --help`, a bare range name matches start/end
  ranges; push/pop ranges (what `torch.cuda.nvtx.range_push` emits) use a suffix such as `"Range A]"`.
- Before/after comparison of one kernel, replay overhead, and whether Triton kernel names match
  `--kernel-name` as expected.
