# Nsight Compute (ncu)

Status: checked on 2026-09-24 with ncu 2025.3.1 on a B300 SXM6 node (driver 580.173.02, CUDA 13.0).
Performance counters are blocked for non-admin users, so no kernel metrics have been collected yet.
Nothing under "Not yet verified" has produced a report on this cluster.

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

## Gotchas

- `ERR_NVGPUCTRPERM` on every collection: the driver has `RmProfilingAdminOnly: 1`. The fix is admin-side:
  set the `nvidia` module option `NVreg_RestrictProfilingToAdminUsers=0` (modprobe config, then reload the
  module or reboot), or grant sudo for `ncu`. Until then, use `torch.profiler` or `do_bench`.
- On the permission error the target still runs to completion, but ncu exits with code 1, so the script's
  own success output does not mean profiling worked.
- `--launch-skip` counts only launches that match the `--kernel-name` filter;
  `--launch-skip-before-match` counts all launches (from `ncu --help`).

## Not yet verified

Blocked on counter permissions. These flags exist in `ncu --help` for 2025.3.1, but none has produced a
report here:
- One kernel, warmup skipped:
  `ncu --kernel-name regex:add_kernel --launch-skip 2 --launch-count 1 --section SpeedOfLight -o out -f ...`
- Memory and roofline sections: `--section MemoryWorkloadAnalysis`, `--section SpeedOfLight_RooflineChart`.
- Export for scripted comparison: `ncu --import out.ncu-rep --csv --page raw`, `--print-summary`.
- NVTX filtering with `--nvtx --nvtx-include`. Per `ncu --help`, a bare range name matches start/end
  ranges; push/pop ranges (what `torch.cuda.nvtx.range_push` emits) use a suffix such as `"Range A]"`.
- Before/after comparison of one kernel, replay overhead, and whether Triton kernel names match
  `--kernel-name` as expected.
