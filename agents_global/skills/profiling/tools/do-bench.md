# triton do_bench (op-level timing)

Status: general guidance, not yet exercised in a verified run on this cluster.

Use to answer "is this op faster" in isolation, quickly, before any end-to-end run. For which
kernels inside the op changed, see `torch-profiler.md`.

## Timing

- `triton.testing.do_bench(fn, warmup=..., rep=...)` handles warmup, CUDA sync, and repetitions. Report the
  min (or a low quantile) across several calls, plus the median.
- For hand-rolled timing, use `torch.cuda.Event(enable_timing=True)` pairs around the call, with warmup
  iterations first and `torch.cuda.synchronize()` before reading.
- Time forward and backward together when the change touches autograd; a faster forward can hide a slower
  backward.
- Use the real shapes and dtypes from the model (log them from a trace's `Input Dims` if unsure).

## Correctness first

- Compare against the old path before timing: `torch.equal` for outputs and gradients when the change
  should be exact; fp8 tensors compared via `.view(torch.uint8)`.
- If a test fails, run it on the unmodified commit to show whether the failure predates the change.

## Pitfalls

- Op benchmarks only cover the code you included. Anything the model runs around the op (permutes,
  copies, their backward) is invisible here; confirm end to end.
- Don't run op benchmarks on GPUs an end-to-end timing run is using.
