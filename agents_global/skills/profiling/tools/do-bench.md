# triton do_bench (op-level timing)

Status: checked against triton 3.7.1 source and measured on one H200 (torch 2.13). Numbers below are from that GPU.

Use to answer "is this op faster, and by how much" in isolation, quickly, before any end-to-end run. For which
kernels inside the op changed, see `torch-profiler.md`.

## Comparing implementations: `scripts/bench_ops.py`

1. Write `inputs/cases.py` in the investigation, with the reference implementation as the first label of every case.
   Use the model's real shapes and dtypes (a trace's `Input Dims`, captured with `record_shapes=True`, lists them).
   The script's docstring has an example that times forward and backward together; do that when the change
   touches autograd, since a faster forward can hide a slower backward.
2. Run it with the project's interpreter from the investigation root, e.g.
   `uv run --no-sync python <skill>/scripts/bench_ops.py inputs/cases.py --check --memory --csv derived/op_bench.csv`.
3. Read the table. `check vs first label` must say `ok` (or the change is not a pure speedup). `first label /
   this` is the speedup over the reference (median over median; above 1x is faster). Trust it only when the two
   rows' p20 to p80 ranges do not overlap.
4. If the medians are under about 20 us, rerun with `--cudagraph` (see below) and report that ratio too.
5. Confirm end to end: the op benchmark covers only the code in the callable.

Optional parts of a cases file (the script's docstring has the details):
- A third case element `{"flops": F, "bytes": B}` adds TFLOP/s and GB/s columns from each median. Say in the notes
  what the byte count covers (read plus write, or one link direction).
- `teardown()` runs once after all timing, to release contexts or communication buffers.
- Give every label its own output buffer. Arms that write into one shared buffer and return it make `--check`
  compare the buffer with itself, so it passes whatever the arms compute.
- torch 2.14's profiler prints `USDT ...` lines to stdout; pipe through `grep -v '^USDT'` before saving tables.
- The most faithful production calling convention for a launch-level case: wrap the real launcher (`mock.patch.object`) during one real training step, record its kwargs, clone the per-step device metadata it was given (pointer tables, counts, offsets), and replay the launcher with identical arguments in each arm. Nothing about routing or buffer offsets is reimplemented in the cases file.

## Power cap and clocks

Measured 2026-10-21/22 on 8x H200 (700 W cap), Triton 3.8, torch 2.14.

- Dense BF16 GEMMs hit the 700 W software power cap within about 0.3 s of sustained work, and the SM clock falls
  from 1980 MHz to about 1450 MHz (throttle reason `0x4`, SW power cap). `do_bench`'s default 25 ms warmup ends
  long before that, so the first callable timed in a process runs partly unthrottled and gets a fast lower tail
  (p20 far below the median), biasing whichever arm comes first. Pass `--warmup 1000` (1 s per callable), or put a
  sacrificial case first; the tables then report power-capped steady state, and should say so.
- Back-to-back bursts right after idle (e.g. the 10 traced calls after a cool-down) ran about 15% shorter than the
  steady-state medians. Inside an end-to-end step, GEMMs that alternate with memory-bound kernels and communication
  logged a median near 1935 MHz while the per-launch benchmark of the same GEMMs sat near 1710 MHz, so a per-launch
  ranking at the cap need not hold end to end.
- Times also moved 5 to 10% with data values (random vs zeros change power draw): give every arm the same realistic
  random inputs.
- `bench_ops.py` times labels one after another. For 1 to 5% effects, check order: rerun with the labels reversed
  (compare with `scripts/bench_compare.py`), or time with a harness in `inputs/` that warms up about 4 s, then
  alternates arm order over several rounds of `do_bench` and takes the median of rounds (1 to 5% spread).
- Log clocks during every timing run whose arms might sit at different power states: start
  `nvidia-smi --query-gpu=timestamp,index,clocks.sm,power.draw,temperature.gpu,clocks_event_reasons.active
  --format=csv -lms 100 > derived/<run>_clocks.csv &` before the run, kill it after, then
  `scripts/gpu_clocks.py ARM=<log> ...` compares busy-sample clocks and throttle reasons. Locking clocks needs admin
  rights.
- One clock log per arm inside a multi-arm `bench_ops.py` process: in the cases file, wrap each callable so that its first call after the label changes stops the running `nvidia-smi` and starts a new one writing `<prefix>_<label>.csv` (one rank per node starts it, e.g. local rank 0). `bench_ops.py` calls each label contiguously (warmup, then timed calls), so each file covers exactly one arm and needs no timestamp join; feed the files to `gpu_clocks.py LABEL=<file> ...`. Stop the last logger in `teardown()`.
- Arms that cannot share a clock (decide the metric before measuring): measured 2026-10-22 on 8x H200, a GEMM with a peer gather overlapped inside it ran at 1450 to 1550 MHz at the power cap, against 1695 MHz for the unfused gather then GEMM (input-gradient GEMM: 1500 to 1730 vs 1972 MHz), because the unfused sequence's memory-bound gather phase lets the clock recover. Lower clocks are a cost of the fused design, not noise, so matching clocks is impossible. Decide on raw ms with both arms in the same session and power state (sustained loops), and report clock-normalized ms (`ms x arm MHz / reference MHz`) only as a ceiling on what the fusion would give without the cap (here 1.14x raw vs 1.31x normalized). Fix that rule (raw ms, same node, same session, ABBA arm order) before the first timing run; deciding it after seeing both numbers invites picking the flattering one.
- Run-to-run noise of an end-to-end case: a 16 ms 8-rank forward plus backward had p20 to p80 spanning about 5% within one run, while the medians of 4 repeated runs (`--warmup 1000 --rep 2000`, identical clocks) spread only 0.17 to 0.47%. Compare full-run medians, never a single run's percentiles, and compare arms on the same node in the same session: another node of the same type read 1% slower.
- A wide p20 to p80 range together with a higher SM clock than the comparison arm points to GPU idle time (host lag or rank skew), not slower kernels: an 8-rank 3.5 ms step that ran 7.9% slower at 1965 vs 1845 MHz had kernels no slower, and one rank's host about 1.3 ms per step late (`tools/exposed-comm.md`, "Step level").

## Collectives and multi-rank ops: `--distributed`

Plain `do_bench` hangs on callables that run collectives: each rank picks its own call count from its own time
estimate, so ranks issue different numbers of collectives. `bench_ops.py --distributed` uses the slowest rank's
estimate for every rank, adds barriers around each phase, and reports the maximum over ranks in every cell (its
docstring has the details; `--cudagraph` is not supported).

- Launch with the project's torchrun, e.g. `.venv/bin/torchrun --standalone --local-addr=127.0.0.1
  --nproc-per-node=8 <skill>/scripts/bench_ops.py inputs/cases.py --distributed --check --warmup 1000 --rep 2000
  --csv derived/<run>.csv`; inside a Slurm allocation, wrap it in `srun --jobid=<job> --overlap -N1 bash -c '...'`.
- A callable that raises on only some ranks leaves the others waiting in a collective: wrap the run in `timeout`.
- `--trace` writes one trace per rank; `tools/torch-profiler.md` covers analyzing them.
- Peer-to-peer baseline over NVLink: a symmetric-memory peer view is an ordinary tensor
  (`torch.distributed._symmetric_memory`: `local = empty(...)`, `handle = rendezvous(local, group=...)`,
  `peer = handle.get_buffer(peer_rank, shape, dtype)`), so `peer.copy_(...)`, `peer.index_select(...)` and
  `peer.index_copy_(...)` are the torch baselines for a custom peer gather or scatter kernel.
- Reference points, H200 NV18 (nominal 450 GB/s per direction), 2 ranks: a peer `copy_` of 256 to 400 MB reached
  360 to 390 GB/s per direction, one direction alone or both at once, and a Triton row gather from the peer was
  insensitive to launch geometry (grid and block sizes). Locally, a row-pointer gather or scatter of 4 to 8 KiB
  rows read plus wrote about 3.8 TB/s, while `index_copy_` reached about 1.4 TB/s (2.7x slower), so `index_copy_`
  is a weak scatter baseline.
- At 8 ranks (all-to-all, H200 NV18): an SM pull gather reached about 27 GB/s per SM and 316 GB/s per GPU, an SM push 23 to 26 GB/s per SM (45 GB/s per SM at 2 ranks does not carry over), and `copy_` from a symmetric peer view (a copy-engine "Memcpy PtoP") about 200 GB/s per GPU. Design consequences: `../kernels/fusion.md`, "Choosing the gather producer".

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
- Two correct BF16 implementations with different accumulation order fail those defaults on near-zero elements
  (the atol of 1e-5 is far below one BF16 rounding step of the larger elements). Gate such A/Bs with a
  scale-relative error, `max |got - ref| / max |ref|`, against an FP32 or FP64 evaluation of the same inputs, in
  a correctness script in `inputs/`; read `--check`'s max abs diff as a sanity bound only.
- Exact rewrites can be checked exactly: on H200 a Triton GEMM with FP32 accumulation over K in order was bitwise
  equal to CUTLASS (`torch._grouped_mm`) and cuBLAS, so `torch.equal` gated it. In torch 2.14 `torch._grouped_mm`
  rejects `out_dtype=torch.float32` for BF16 inputs; build an FP32-output reference from per-group
  `torch.mm(a, b, out_dtype=torch.float32)`.
- An exactness check of a gather (or of a kernel that fuses one) only means something if the destination rows are poisoned (filled with NaN) before each checked call; otherwise a kernel that skips the gather passes on the rows a previous call left behind.
- Variants selected by an environment variable can be compared bitwise inside one torchrun process: set the variable only around context creation, run each arm on fresh clones of the same inputs and parameters, compare with `torch.equal` per rank and reduce the verdict over ranks, and add a second run of the reference arm, so that run-to-run nondeterminism cannot pass for a variant effect.
- When a fused path can silently fall back to the unfused one (for example when a per-shape config is missing), spying on the dispatch flag or the selected mode is not enough: wrap the fused component's own launcher with a spy and assert its launch count per step (here 3 producer launches per step on every rank, with the expected grid).
- To prove that a device-predicated branch ran (for example a recompute guarded by a device flag), wrap the launcher with `mock.patch.object(module, name, side_effect=spy)` and read the predicate with `.item()` inside the spy, at call time (a host sync, so only in correctness runs outside graph capture). Read after the step, the tensor can already hold a later value from a reused buffer.
- A graph-replay test that rewrites a pointer table (device memory holding source addresses) must keep the new source tensors alive until the replay finishes: the caching allocator hands the freed blocks to the next allocation (a later `clone()`), so the replay reads overwritten memory with no error. One such test failed deterministically on its second replay; a sibling test with the same dangling pattern passed only by luck of allocation order.
- When a numerical test fails by a hair, compare both the result and the reference with an FP64 evaluation before
  blaming the change: a BF16 reference can be the less accurate side.
- If a test fails, run it on the unmodified commit to show whether the failure predates the change. On a new
  architecture, record the baseline's failing tests before changing anything.

## Pitfalls

- Op benchmarks only cover the code you included. Anything the model runs around the op (permutes,
  copies, their backward) is invisible here; confirm end to end.
- `--memory` measures from the allocation just before the call. A forward plus backward callable that starts with
  `x.grad = None` frees the previous call's gradients inside the call, so its peak above that baseline understates
  the transient (it can read lower than the forward-only case). Compare such peaks only across arms with the same
  gradient handling.
- When a host-side limit (a shared-memory budget, a register cap, a size clamp) rewrites a requested config, label each arm by the config that actually runs and skip duplicate points; otherwise two labels time the same kernel, and their noise reads as a tuning signal (a 4-warp x 4-stage request ran as 4 x 3 under a 96 KiB budget at 8 KiB rows).
- Don't run op benchmarks on GPUs an end-to-end timing run is using. Host-bound results move with CPU load on a
  shared node: the same eager forward and backward read 0.37 ms in one run and 0.24 ms in the next, both pinned
  with `taskset -c`. Repeat the run before trusting a host-bound difference.
