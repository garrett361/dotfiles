# torch.profiler traces

Use for kernel-level attribution: inside one op, and especially for diffing two end-to-end runs.

## Op-level kernel breakdown

`scripts/bench_ops.py CASES.py --trace DIR` runs each implementation of an op 10 times (`--trace-iters`) under
the profiler after timing it. Then, per implementation, `top_kernels.py DIR/<case>__<label>.json.gz --whole-trace
--decimals 3 --csv <label>.csv`, and `kernel_diff.py a.csv b.csv --decimals 3` (divide totals by the iteration
count). This
separates, for example, cast overhead from GEMM time, with launch counts. `prof.key_averages().table()`
truncates kernel names, so templated elementwise kernels all look alike there.

## Capture

- Wrap the training loop in `torch.profiler.profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA],
  schedule=schedule(wait=1, warmup=2, active=3, repeat=1), record_shapes=True,
  on_trace_ready=lambda p: p.export_chrome_trace(f"{out}/trace_{rank}.json.gz"))` and call `prof.step()` at the
  end of every step. Each step becomes a CPU-side `ProfilerStep#<n>` range: pass `--launched-in ProfilerStep` to
  `top_kernels.py` (see the window pitfall below), `--annotation ProfilerStep` to `trim_last_step.py`, and
  `--step-marker ProfilerStep` to `timeline_figure.py`. Without `repeat=1` the schedule cycles and each
  cycle's export overwrites the last. Projects with their own step annotation use it instead (prime-rl:
  `forward`, the scripts' default; see `projects/prime-rl.md`).
- `record_shapes` puts `Input Dims` on CPU ops, which identifies call sites and shapes. `with_stack=True` adds
  Python frames, for `trace_events.py --include-python`.
- Keep captures short (a handful of steps) and analyze only a steady-state step: early steps include
  compile, autotuning, and allocator warmup.
- Prefer a scaled-down model that reproduces the full-scale behavior (same per-GPU tokens and context,
  fewer layers). Validate the proxy first: its step-time ratio between arms should match the full model's.
- Capture every arm the same way: same config, steps, and ranks.

## Analysis recipe

For "why doesn't my op-level win show up in step time?", run these on both arms. The answer is usually one of:
the op is a small share of GPU busy time; the GPU idles (host-bound), so saved kernel time becomes idle time;
other kernels got slower or new launches appeared; or the saving is on a rank or stream that does not set the
step time.

1. **Step window.** `top_kernels.py` windows on the last step marker (`--annotation`, `--annotation-index`).
   Check the window length against the logged step time before trusting any number derived from it.
   `trace_events.py <trace> --list-annotations ""` lists the annotation names a trace has.
2. **Busy vs idle.** `top_kernels.py`'s header gives GPU busy time, the union of kernel intervals across all
   streams. Near 100% busy means host overhead and syncs are not the bottleneck; go to kernels. If not, look
   at host gaps (`trace_events.py`, `timeline_figure.py --annotate-gaps`, `step_accounting.py`).
3. **Per-kernel diff.** `top_kernels.py --csv` per arm, then `kernel_diff.py before.csv after.csv`. Same count
   with more time means the op got slower; a count change means launches were added or removed.
4. **Call sites.** `top_kernels.py --by both --csv` per arm, then `kernel_diff.py --key label`, splits each
   kernel by the op that launched it, with `Input Dims`.
5. **Sync cost.** Blocking calls (`cudaStreamSynchronize`, `.item()`, a D2H copy into pageable memory) and
   the GPU idle they cause: `scripts/find_syncs.py`, see `analysis/cuda-syncs.md`.

## Trace format (for extending the scripts)

`trace_events.read_trace(path)` loads `.json` or `.json.gz`; complete events (`ph == "X"`) carry `cat`:
`kernel` (also `gpu_memcpy`, `gpu_memset`), `cpu_op`, `user_annotation` (a `record_function` range; torch
also projects it onto the GPU stream as `gpu_user_annotation`), `cuda_runtime` (`cudaLaunchKernel`, ...), and
`cuda_driver` (`cuLaunchKernel`/`cuLaunchKernelEx`, used by cuBLASLt's `nvjet` GEMMs and JIT kernels such as
TileLang's). A kernel's `args["correlation"]` matches its `cuda_runtime` or `cuda_driver` launch, so
launch-to-kernel mapping must follow both categories; the `cpu_op` events on the launch's thread that enclose
it name the call site.

## Pitfalls

- Categorizing kernels by regex is fragile (shared prefixes, cryptic template names). Print raw top names
  alongside any categories.
- Communication kernels run on side streams and their durations include waiting. Report their deltas
  separately; they may not be on the critical path.
- Rank 0 is representative only under balanced work; otherwise also check the slowest rank.
- Traced step times are inflated, most for host-bound steps. Quote untraced medians for timing. The
  profiler's host overhead also lowers the traced busy fraction: a toy loop was 56% busy in its trace (3.1 ms
  window) while its untraced step was 1.88 ms for 1.7 ms of kernels.
- CPU-side step windows (`top_kernels.py --annotation`, `timeline_figure.py --step-marker`) select kernels by
  GPU start time. When the host runs ahead of the GPU this misplaces them: in a GPU-bound toy loop with 44.5 ms
  of kernels per step, the last three `ProfilerStep` windows held 4.5, 3.5 and 203 ms. `top_kernels.py
  --launched-in ProfilerStep` (by launch) or `--from-annotation ProfilerStep --from-index -2 --to-annotation
  ProfilerStep` (GPU-side) gave 44 to 45 ms. A step that syncs the host each iteration, as prime-rl's does, is
  not affected.
