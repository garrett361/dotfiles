# Nsight Compute (ncu)

Verified on H200 (sm90, 2026-10-10 and 2026-10-11) with ncu 2025.3.1. On the B300 cluster performance counters are
admin-only, so ncu collects nothing there; see "Cluster notes" at the end.

## When to use

- Why a single kernel is slow: achieved bandwidth and FLOPs against peak, occupancy, stalls, cache behavior.
- Comparing one kernel's metrics before and after a change.
- Op-level scripts only. Replay-based measurement makes whole training runs impractical.

## Verified recipes

- Binaries: `ncu` on `PATH` is `/usr/local/cuda-12.9/bin/ncu`, a shell wrapper (as is
  `/usr/local/cuda-13.0/bin/ncu`) that runs the newest install under `/opt/nvidia/nsight-compute/`
  (2025.2.1 and 2025.3.1 exist; both wrappers report 2025.3.1). Same layout on login and compute nodes.
- Check counter permissions on a compute node before planning any ncu work:
  `grep RmProfilingAdminOnly /proc/driver/nvidia/params`. A value of `1` means only admins can profile.
- `ncu --list-sections` works without counters and maps each display name to the identifier `--section`
  takes: `SpeedOfLight`, `MemoryWorkloadAnalysis`, `Occupancy`, `LaunchStats`, `WarpStateStats` (Warp
  State Statistics), `SourceCounters`, `ComputeWorkloadAnalysis`, `SchedulerStats`, `SpeedOfLight_RooflineChart`.
- Run on one GPU, wrapping `uv run` directly; ncu attaches to the Python child process. Inside an existing
  allocation, add a step: `srun --jobid=<job> --overlap bash -lc 'export CUDA_VISIBLE_DEVICES=<gpu>; ncu ... uv run
  --no-sync python script.py'`. Without one: `srun -p <partition> -N1 --gpus=1 --time=00:20:00 bash -lc 'ncu ...'`.

## Collecting and reading counters

Counters work for normal users on the `prime-nebius-puku-h200-gpu-*` nodes (ncu 2025.3.1 via
`/usr/local/cuda-13.0/bin/ncu`, SLURM job 3569).

- One kernel, one launch, with per-line source counters:
  `ncu --target-processes all -k regex:<name> -s 1 -c 1 --section SpeedOfLight --section SourceCounters --section LaunchStats --import-source yes -o out -f uv run --no-sync python script.py`.
  `uv run` starts Python as a child; `--target-processes all` is the default (`ncu --help`), and a child
  was profiled without it. `-s 1` skipped the first matching launch and `-c 1` stopped after one. These
  three sections took 13 replay passes; `--set full` took 38 on every kernel tried.
- Source correlation needs a kernel built with line info (CUDA `-lineinfo`, CuTe DSL `CUTE_DSL_LINEINFO=1`).
  Triton emits it by default (`TRITON_DISABLE_LINE_INFO=1` turns it off) and maps to the kernel's `.py`.
  `ncu -i out.ncu-rep --page source --print-source cuda,sass --csv` prints one row per source line
  (metrics summed over its instructions) followed by its SASS rows. `--print-source cuda` alone prints
  the file with no metric columns. `--import-source yes` embeds the source file in the report.
  Rank lines with `scripts/ncu_source_lines.py` (one table row per line and launch, `--view sass` per instruction).
- A `long_sb` (long scoreboard) stall is charged to the instruction that waits for a global or local load's
  result, not to the load: in a gather `v = x[idx]; out = exp(v)`, most `long_sb` samples sat on the `exp` line.
- ncu locks clocks to base by default (`--clock-control base`): the report showed `SM Frequency 1.50 GHz`
  on an H200 whose maximum is 1.98 GHz. Only the SM clock is locked: DRAM stayed at 3.20 GHz, and a
  memory-bound gather ran 259 us with and without `--clock-control none` (SM 1.96 GHz), with the same
  DRAM and L2 throughput %. SM-side percentages (L1, Compute) are per SM cycle, so they read higher at base
  clock (L1 38% vs 29%), and compute-bound kernels run longer under ncu. Take timings from events, and the
  why from ncu.
- Launch Statistics "Registers Per Thread" is the cubin's `REG:` (`cuobjdump --dump-resource-usage`) but
  never below 16: `REG:12` and `REG:14` kernels showed 16, a `REG:27` Triton kernel 27. The 8-register
  allocation is the raw metric `launch__registers_per_thread_allocated` (32 for that kernel).
- Triton kernels keep the Python function's name (`-k regex:gather_scale` matched `gather_scale_kernel`).
  An autotuned kernel launches every config under that name during tuning (44 matching launches in a run with 3 configs), so
  `-s`/`-c` counts can land on a tuning launch. Wrap the steady-state calls in
  `torch.cuda.nvtx.range_push("steady")` / `range_pop()` and select with
  `--nvtx --nvtx-include "steady]" -k regex:<name> -c 1` (the `]` marks a push/pop range). Do not profile
  every launch (`-c` large): profiling the tuning launches changed the chosen config (BLOCK 4096 vs 256).

### TileLang kernels

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

## Reading a report: bandwidth, latency or occupancy

- SpeedOfLight first. DRAM or L2 Throughput near 80% or more of peak: bandwidth-bound; fix bytes moved
  (fusion, coalescing, reuse). Memory Workload Analysis gives hit rates; an "uncoalesced global accesses"
  note in Source Counters names excessive sectors.
- Both Memory and Compute throughput well below peak: latency-bound. WarpStateStats says which stall
  dominates; `scripts/ncu_source_lines.py` says where. `long_sb` means waiting on global/local memory,
  `barrier` on `__syncthreads`, `mio`/`lg` on full load/store queues, `wait` on fixed-latency dependencies.
- Occupancy: compare Achieved with Theoretical Occupancy, and read the "Block Limit" rows (registers,
  shared memory, warps) for what caps it. Low occupancy matters most when latency-bound.
- These cutoffs are rules of thumb, not ncu outputs; the OPT notes under each section also estimate a speedup.

## Gotchas

- `ERR_NVGPUCTRPERM` on every collection means counters are admin-only (`RmProfilingAdminOnly: 1`); see the
  B300 cluster notes for the fix. The target still runs to completion, but ncu exits with code 1, so the
  script's own success output does not mean profiling worked.
- `--launch-skip` counts only launches that match the `--kernel-name` filter;
  `--launch-skip-before-match` counts all launches (from `ncu --help`).
- Cross-rank kernels are unreliable under ncu (2026-10-22, 8x H200, NVLink): with one `ncu --target-processes all` wrapping torchrun, profiling two ranks whose kernels read each other's memory failed with `==ERROR== UnknownError` for the NVLink (`nvlrx__*`) and peer-aperture L2 (`lts__t_sectors_srcunit_tex_aperture_peer*`) metrics; basic metrics on one rank sometimes succeeded. Fall back to timing (`tools/do-bench.md`, `bench_ops.py --distributed`).

## Not yet verified

- Before/after comparison of one kernel, and replay overhead.

Verified on H200 2026-10-11: `ncu -i out.ncu-rep --print-summary per-kernel` (min/max/average per kernel
over launches), and NVTX push/pop filtering as above.

## Cluster notes

### B300 (2026-09-24, ncu 2025.3.1, driver 580.173.02, CUDA 13.0)

- `ncu --query-metrics --devices 0` prints `Device NVIDIA B300 SXM6 PC (GB110)`, and `gb110` is in
  `ncu --list-chips`, so 2025.3.1 recognizes the chip, but every collection fails with `ERR_NVGPUCTRPERM`:
  the driver has `RmProfilingAdminOnly: 1`. No kernel metrics have been collected there.
- The fix is admin-side: set the `nvidia` module option `NVreg_RestrictProfilingToAdminUsers=0` (modprobe config,
  then reload the module or reboot), or grant sudo for `ncu`. Until then, use `torch.profiler` or `do_bench`.
- Slurm there: `srun -p all -N1 --gpus=1 --time=00:20:00 bash -lc 'ncu ... uv run python script.py'`.
