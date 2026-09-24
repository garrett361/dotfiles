# Nsight Systems (nsys)

Status: verified 2026-09-24 with `/opt/nvidia/nsight-systems/2025.3.2/bin/nsys` (2025.3.2.474) on an 8xB300
Slurm compute node (driver 580.173.02, CUDA 13.0), torch 2.13.0+cu130, NCCL 2.29.7. Toy workloads only
(bf16 4096 matmul + GELU; 2-rank all_reduce), not a real training run.

## When to use

- Whole-timeline view with lower overhead than `torch.profiler`: CPU threads, CUDA API, kernels, memcpys,
  NCCL, and OS runtime on one timeline.
- Host gaps, launch overhead, synchronization stalls, and stream overlap across a full step.
- Multi-process (per-rank) captures under a launcher such as `srun` or `torchrun`.

## Binary

- Use `N=/opt/nvidia/nsight-systems/2025.3.2/bin/nsys` (same version as the CUDA 13.0 toolkit's nsys).
- `nsys` on `PATH` is `/usr/local/cuda-12.9/bin/nsys` (2025.1.3). It also captured fine but warns that
  device-side CUDA event trace is on (disable with `--cuda-event-trace=false`).
- `/opt/nvidia/nsight-systems/2026.1.3` exists on the login node only, not on compute nodes.
- `nsys stats` and `nsys export` run fine on the login node (no GPU needed).

## Verified recipes

Run from the project dir so `uv run` resolves the venv; nsys follows child processes.

Full capture (single GPU):

```bash
$N profile -t cuda,nvtx,osrt -s none --cpuctxsw=none -o out --force-overwrite true uv run python toy.py
```

Steady-state only, via CUDA profiler API. Call `torch.cuda.profiler.start()` / `.stop()` around the
iterations to keep:

```bash
$N profile -t cuda,nvtx,osrt -s none --cpuctxsw=none \
  --capture-range=cudaProfilerApi --capture-range-end=stop -o out --force-overwrite true uv run python toy.py
```

Steady-state only, via an NVTX range. Wrap the iterations in `torch.cuda.nvtx.range_push("capture")` /
`range_pop()`; the env var is required (see Gotchas):

```bash
NSYS_NVTX_PROFILER_REGISTER_ONLY=0 $N profile -t cuda,nvtx,osrt -s none --cpuctxsw=none \
  --capture-range=nvtx --nvtx-capture=capture --capture-range-end=stop -o out --force-overwrite true \
  uv run python toy.py
```

Both captured exactly the 10 intended iterations (10 instances of each kernel and NVTX range).

One report per rank under torchrun (`--no-python` lets torchrun launch nsys; `%q{RANK}` expands per rank):

```bash
uv run torchrun --nproc-per-node 2 --no-python $N profile -t cuda,nvtx,osrt -s none --cpuctxsw=none \
  -o "out_rank%q{RANK}" --force-overwrite true python dist.py
```

Wrapping the launcher instead (`$N profile ... uv run torchrun --nproc-per-node 2 dist.py`) gives one
report with both ranks. Both showed `ncclDevKernel_AllReduce_Sum_bf16_RING_LL` in the kernel summary.

## Summaries and export

- `$N stats -r cuda_gpu_kern_sum,nvtx_sum out.nsys-rep` prints kernel and NVTX tables (writes
  `out.sqlite` next to the report on first use). Add `-f csv` for CSV, `-q` to drop the progress lines.
  `osrt_sum` gives OS runtime call totals.
- `$N export --type sqlite --force-overwrite true -o out.sqlite out.nsys-rep` for scripted analysis.
- Kernel totals from the sqlite (no `sqlite3` CLI on the login node, so use Python):

```bash
uv run python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); [print(r) for r in c.execute('select s.value, count(*), sum(k.end-k.start)/1e3 as us from CUPTI_ACTIVITY_KIND_KERNEL k join StringIds s on s.id=k.demangledName group by s.value order by us desc limit 5')]" out.sqlite
```

  Joining on `k.shortName` instead merges templated kernels (GELU and mul both become
  `vectorized_elementwise_kernel`).

## Overhead and size (toy, one B300)

- Steady-state per-iteration time: 0.1126 ms untraced vs 0.1145 ms traced (about +2%).
- First-iteration cost grows (loop 0.39 s to 0.63 s), and whole-command wall time went from about 6.5 s
  to 26 to 30 s, mostly nsys startup and report generation after the app exits.
- Report size about 0.7 MB for both 20 and 200 iterations (startup dominates); 0.1 MB with a capture range.

## Gotchas

- `-s none --cpuctxsw=none` is needed: `perf_event_paranoid` is 4 and there is no root, so CPU sampling
  and context-switch tracing are unavailable (`nsys status -e` reports Fail).
- NVTX capture range with `torch.cuda.nvtx` silently produced "No reports were generated" until
  `NSYS_NVTX_PROFILER_REGISTER_ONLY=0` was set: torch pushes unregistered NVTX strings.
- With `--capture-range-end=stop`, the app blocks inside the stop call (about 12 s here) while nsys
  flushes. Don't time across the stop point.
- `osrt` on the rank that hosts the TCPStore (rank 0) traced about 900k `accept` calls: 12 MB report vs
  1.2 MB for rank 1. Drop `osrt` from `-t` if OS runtime calls aren't the question.
- `nvtx_sum` reports CPU-side range durations: `iter0` included cuBLAS init (628 ms vs about 30 us for
  later iterations). Skip warmup iterations when reading it.
- No `/usr/bin/time` on compute nodes; use the bash `time` builtin.

## Not yet verified

- Per-rank capture under `srun` (multi-node) rather than torchrun, e.g. `%q{SLURM_PROCID}` in `-o`.
- Real training runs: overhead and report size at full model scale, and `--cuda-graph-trace` for graphs.
- `nvtx_gpu_proj_sum` (NVTX ranges projected onto GPU time) and `--gpu-metrics-devices` sampling.
- Running the 2026.1.3 binary (not present on compute nodes).
