# triton do_bench (op-level timing)

Status: checked against triton 3.7.1 source and measured on one H200 (torch 2.13). Numbers below are from that GPU.

Use to answer "is this op faster, and by how much" in isolation, quickly, before any end-to-end run. For which
kernels inside the op changed, see `torch-profiler.md`.

## Comparing implementations: `scripts/bench_ops.py`

1. Write `cases.py` in the investigation root, with the reference implementation as the first label of every case.
   Use the model's real shapes and dtypes (a trace's `Input Dims`, captured with `record_shapes=True`, lists them).
   The script's docstring has an example that times forward and backward together; do that when the change
   touches autograd, since a faster forward can hide a slower backward.
2. Run it with the project's interpreter from the investigation root, e.g.
   `uv run --no-sync python <skill>/scripts/bench_ops.py cases.py --check --memory --csv derived/op_bench.csv`.
3. Read the table. `check vs first label` must say `ok` (or the change is not a pure speedup). `first label /
   this` is the speedup over the reference (median over median; above 1x is faster). Trust it only when the two
   rows' p20 to p80 ranges do not overlap.
4. If the medians are under about 20 us, rerun with `--cudagraph` (see below) and report that ratio too.
5. Confirm end to end: the op benchmark covers only the code in the callable.

## What `do_bench` measures

`triton.testing.do_bench(fn, warmup=25, rep=100, grad_to_none=None, quantiles=None, return_mode="mean")`:

- It returns the **mean** by default (its docstring says median, which is wrong). `quantiles=[0.5, 0.2, 0.8]`
  returns those quantiles instead and overrides `return_mode`; `return_mode="all"` returns every sample.
- `warmup` and `rep` are millisecond budgets, not counts. It times 5 calls to estimate the per-call time, then runs
  `rep / estimate` timed calls: a 1.4 ms matmul with `rep=20` gave 5 samples.
- The first call (compile, autotune) happens before anything is timed.
- Before every timed call it zeroes a 256 MiB buffer (82 us on H200) to flush L2, so times are cold-L2. Inputs
  that fit in L2 (60 MiB on H200) can run faster inside the model: a 16 MiB in-place multiply took 13.5 us under
  `do_bench` and 6.4 us under `do_bench_cudagraph` (3 us of that gap is the event overhead below); at 512 MiB
  the two agree within 1%.
- Each call has its own event pair, which adds about 3 us (an empty `fn` reads 2.9 us). Under about 20 us that
  compresses ratios: a 256-element add read 5.0 us against 1.0 us with `do_bench_cudagraph`.
- Host time leaks in. The flush gives the host about 80 us of lead per call; beyond that the GPU waits for launches
  and the event pair counts the wait (100 us of host work per call read as 58 us, 500 us as 462 us). A large gap
  between `do_bench` and `do_bench_cudagraph` means the op is host-bound; which number matters depends on whether
  the real loop is. Calling a `@cute.jit` function directly costs about 7 ms of host time per call, against 4 us
  for a cached TVM-FFI executor: read `cute-dsl.md` before timing a CuTe DSL kernel.
- If `fn` runs a backward, pass `grad_to_none=[...]` or set `.grad = None` inside `fn`; otherwise every call also
  accumulates into `.grad` (160 us against 109 us measured).

`do_bench_cudagraph(fn, rep=20, quantiles=None, return_mode="mean")` captures `rep / estimate` calls into one CUDA
graph, replays it 10 times, and returns per-call times: no L2 flush, no per-call event or launch overhead, and
`fn` must be capturable (no host syncs). `bench_ops.py --cudagraph` uses it.

## Timing regions of a script or project: `scripts/cuda_timer.py`

- Copy it in: `with timer("name"):` around each region records CUDA events without host syncs, and
  `timer.table()` reports count, total, mean, median, min and max per region.
- `timer.reset_after_warmup(n)` drops the first `n` entries of every region. That is `n` steps only for regions
  entered once per step; otherwise leave the warmup steps outside the timer.
- An event pair times its stream's timeline, idle gaps included: if the host launches slower than the GPU runs,
  the region reads as host time.

## Correctness first

- `bench_ops.py --check` compares each output with the first label's under `torch.testing.assert_close`'s
  default tolerances (bf16: rtol 1.6e-2, atol 1e-5). When the change should be exact, compare outputs and
  gradients with `torch.equal` (it accepts float8 in torch 2.13).
- If a test fails, run it on the unmodified commit to show whether the failure predates the change.

## Pitfalls

- Op benchmarks only cover the code you included. Anything the model runs around the op (permutes,
  copies, their backward) is invisible here; confirm end to end.
- Don't run op benchmarks on GPUs an end-to-end timing run is using. Host-bound results move with CPU load on a
  shared node: the same eager forward and backward read 0.37 ms in one run and 0.24 ms in the next, both pinned
  with `taskset -c`. Repeat the run before trusting a host-bound difference.
