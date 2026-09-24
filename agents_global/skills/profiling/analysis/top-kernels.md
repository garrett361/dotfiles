# Most expensive kernels

Answers "where should I optimize?": which kernels take the step's time (rank by total), which single launches
are expensive (rank by time per call), and which op launched each kernel. Templated names such as
`elementwise_kernel<128, 4, MulFunctor<float>>` hide their caller, so attribute them to call sites before
drawing conclusions.

## torch.profiler route: `scripts/top_kernels.py`

Works on any `torch.profiler` chrome trace (stdlib only, run with `python3`). The default window is the last
step: from the last CPU-side `user_annotation` named `forward` to the last GPU event, as in
`scripts/trim_last_step.py`. It takes about 10 to 15 s on a 28 MB trace.

- `python3 top_kernels.py trace_0.json.gz`: tables by kernel name.
- `--by site`: group by the launching op and its `Input Dims`; `--by both`: one row per site and kernel.
- `--stream main`: only the stream with the most kernel time (or pass a stream id).
- `--csv out.csv` writes every row with raw kernel names; `--minmax` adds min/max columns; `--top N`,
  `--min-calls N` (per-call ranking), `--name-width N`, `--annotation NAME`, `--whole-trace`.

Output: a header (window length, GPU busy time as the union of kernel intervals, NCCL vs non-NCCL sums,
kernel time per stream), then three tables: non-NCCL by total, non-NCCL by mean time per call, and NCCL by
total. Each row has total ms, % of GPU busy, % of window, calls, mean and median ms. Labels longer than the
name column are listed in full under the table, by rank.

Call sites follow the kernel's `args["correlation"]` to its `cuda_runtime` / `cuda_driver` launch, then take
the `cpu_op` events enclosing the launch on the same thread. A custom op is shown by itself
(`prime_rl::dsv4_sparse_attn_backward [dims]`); an `aten::` op gets its nearest non-aten ancestor, such as an
autograd node, a compiled region, or a custom autograd Function
(`MulBackward0 > aten::mul [1,32768,4,4096],...`); an NCCL kernel is shown as the collective that issued it
plus the tensor dims (`prime_rl_collectives::all_to_all_single [196608,4096]`).

## Reading the tables

- Check the window against the logged step time, and busy/window before anything else: near 100% busy means
  kernels, not host gaps, set the step time.
- NCCL durations include waiting for peers. Compare NCCL and compute totals across ranks: the rank with the
  most compute and the least NCCL is the critical path, and the others' extra NCCL time is waiting. In the
  DSV4 Flash proxy (cp 8), rank 0 had 1729 ms compute and 322 ms NCCL, rank 7 had 1854 ms and 194 ms; the
  causal FP8 indexer grew from 11 ms on CP rank 0 to 114 ms on CP rank 7.
- NCCL kernels on the main compute stream serialize with compute; side-stream ones may overlap.
- Selective activation checkpointing recomputes forward ops inside the backward node that first needs them.
  The same op and shapes then appear twice, for example `compiled 0/0 > aten::cat [...]` (forward) and
  `prime_rl_dsv4_mhc_post_bda (bwd) > aten::cat [...]` (recompute) with equal time: add both for the op's
  real cost.
- A site can launch several kernels, so its mean and median mix them; use `--by both` for per-kernel rows.
- Rows group raw kernel names. Distinct kernels can shorten to the same label; those get `#2`, `#3`, and the
  CSV has the raw names.
- `--whole-trace` includes compile and autotuning: in the DSV4 trace, the `@triton.autotune`d mHC kernels
  (`_triton_hpb_*`, 12 to 24 launches per step but 5413 to 10605 over the trace) topped the table.

## nsys route: `cuda_gpu_kern_sum`

Verified 2026-09-24 on one 8xB300 node with the DSV4 Flash proxy (`/opt/nvidia/nsight-systems/2025.3.2`).
A prime-rl config with `deployment.type = "single_node"` and no `[slurm]` section runs torchrun locally, so
inside a one-node allocation (here an sbatch script with `--gres=gpu:8 --exclusive --time=00:20:00`), nsys
can wrap the entrypoint and follows all 8 ranks into one report:

```bash
N=/opt/nvidia/nsight-systems/2025.3.2/bin/nsys
cd <prime-rl worktree>
$N profile -t cuda,nvtx -s none --cpuctxsw=none -o <out> --force-overwrite true \
  uv run sft @ <config.toml> --run.name <unique name> --max-steps 5
```

- `$N stats -q -r cuda_gpu_kern_sum <out>.nsys-rep` gives total, instances, avg, median, min, max per
  kernel, summed over every rank and the whole capture. Unwindowed it is dominated by step-1 autotuning
  (the `_triton_hpb_*` kernels were the top three rows, 43% of kernel time), so restrict it.
- `--filter-time <start_ns>/<end_ns>` keeps events overlapping the window, still summed over all GPUs
  (the 6 per-rank sparse-attention backward launches showed as 48 instances). The times are the `start` /
  `end` values of `CUPTI_ACTIVITY_KIND_KERNEL` in the sqlite export that `stats` writes next to the report.
- Per rank, query the sqlite by `deviceId`. prime-rl emits no NVTX ranges, but each SFT step ends with a
  cluster of fused AdamW kernels, so the last step runs from the end of the second-to-last cluster to the end
  of the last one:

```python
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
adam = c.execute("select k.start, k.end from CUPTI_ACTIVITY_KIND_KERNEL k join StringIds s on s.id = k.demangledName"
                 " where k.deviceId = 0 and s.value like '%FusedAdamMathFunctor%' order by k.start").fetchall()
ends = [e for (s, e), (s2, _) in zip(adam, adam[1:] + [(float("inf"), 0)]) if s2 - e > 100e6]
lo, hi = ends[-2], ends[-1]
for row in c.execute("select s.value, count(*), sum(k.end - k.start) / 1e6 as ms from CUPTI_ACTIVITY_KIND_KERNEL k"
                     " join StringIds s on s.id = k.demangledName where k.deviceId = 0 and k.start > ? and k.end <= ?"
                     " group by s.value order by ms desc limit 20", (lo, hi)):
    print(row)
```

Agreement with torch.profiler (separate runs, same commit and config, rank 0, last step): the same 8410
kernels, window 2343.9 vs 2340.8 ms, and every non-NCCL kernel among the top 20 within about 3% in total and
median.
NCCL differed more between runs (AllGather 61.1 vs 39.7 ms) because its time is mostly waiting.

## Which route

- torch.profiler: per-rank traces with step annotations and call sites with shapes, which name the op
  behind templated kernels. In prime-rl it needs only `--trace-path`.
- nsys: no code or config change, every rank in one report, and CPU/CUDA API rows on the same timeline, but
  kernel names only (no op or shape context without NVTX) and it needs manual windowing. Cost on the proxy:
  step 1 (compile included) took 3m13s vs 2m11s in the torch.profiler run, the report was 113 MB (plus a
  271 MB sqlite), and `stats` took about 9 s on the login node.
- Steady-state step time was 2.3 s (MFU 43%) under both, so neither changed it visibly for this GPU-bound
  step. Timing claims still come from untraced runs.
