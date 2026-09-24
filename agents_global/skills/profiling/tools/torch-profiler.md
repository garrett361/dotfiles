# torch.profiler traces

Use for kernel-level attribution: inside one op, and especially for diffing two end-to-end runs.

## Op-level kernel breakdown

Wrap about 10 fwd+bwd iterations, after about 5 warmup iterations, in
`torch.profiler.profile(activities=[ProfilerActivity.CUDA])`, then print
`prof.key_averages().table(sort_by="self_device_time_total")`. Divide by the iteration count to get
per-iteration numbers. This separates, for example, cast overhead from GEMM time.

## Capture

- `torch.profiler.profile(activities=[CPU, CUDA], record_shapes=True)` and `export_chrome_trace` per rank.
  `record_shapes` puts `Input Dims` on CPU ops, which identifies call sites and shapes.
- Keep captures short (a handful of steps) and analyze only a steady-state step: early steps include
  compile, autotuning, and allocator warmup.
- Prefer a scaled-down model that reproduces the full-scale behavior (same per-GPU tokens and context,
  fewer layers). Validate the proxy first: its step-time ratio between arms should match the full model's.
- Capture every arm the same way: same config, steps, and ranks.

## Load

`events = json.load(gzip.open(path))["traceEvents"]`. Useful event kinds (`ph == "X"`):
- kernels: `cat == "kernel"` (also `gpu_memcpy`, `gpu_memset`)
- CPU ops: `cat == "cpu_op"`
- CUDA runtime calls: `cat == "cuda_runtime"` (`cudaLaunchKernel`, `cudaStreamSynchronize`, ...)
- CUDA driver calls: `cat == "cuda_driver"` (`cuLaunchKernel`): JIT kernels such as TileLang's launch this
  way, so launch-to-kernel mapping must follow both categories
- user annotations from `record_function(...)`

## Analysis recipe

1. **Step window.** Anchor on a per-step annotation and take kernels after the start of the last step.
   Each `record_function` annotation appears twice: as a CPU `user_annotation` and as its projection onto a
   GPU stream (`gpu_user_annotation`). Select by `cat`, not by counting. Check the window length against the
   logged step time before trusting any number derived from it.
2. **Busy vs idle.** GPU busy time is the union of kernel intervals across all streams. If the GPU is near
   100% busy, host overhead and syncs are not the bottleneck; go to kernels. If not, look at host gaps.
3. **Per-kernel diff.** Sum `dur` by kernel name (truncated to about 95 characters) per arm, sort by
   absolute difference, and print launch counts. Same count with more time means the op got slower; a count
   change means launches were added or removed.
4. **Call sites.** A kernel's `args["correlation"]` matches its `cuda_runtime` or `cuda_driver` launch event. The `cpu_op`
   events on the same `tid` enclosing the launch (innermost two or three) plus `Input Dims` name the source.
5. **Sync cost.** For blocking calls (`cudaStreamSynchronize`, `cudaDeviceSynchronize`,
   `cudaEventSynchronize`, synchronous `cudaMemcpy`, and a D2H `cudaMemcpyAsync` into pageable memory, where
   `.item()` waits), record host duration, enclosing CPU op stack, and the GPU idle it causes.
   `scripts/find_syncs.py` does this; see `analysis/cuda-syncs.md`.

## Pitfalls

- Categorizing kernels by regex is fragile (shared prefixes, cryptic template names). Print raw top names
  alongside any categories.
- Communication kernels run on side streams and their durations include waiting. Report their deltas
  separately; they may not be on the critical path.
- Rank 0 is representative only under balanced work; otherwise also check the slowest rank.
- Traced step times are inflated. Quote untraced medians for timing.
