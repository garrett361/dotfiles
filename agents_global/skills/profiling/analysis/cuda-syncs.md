# Finding CUDA host syncs

Goal: every point in a steady-state step where the host blocks on the GPU, each with an op, a Python file:line,
a count per step, and a cost. Verified 2026-09-24 on torch 2.13.0+cu130, 8xB300, prime-rl SFT (DeepSeek V4 Flash
6-layer proxy: 121 syncs per step, identical on every step and rank).

## Which method answers what

| Method | Gives | Misses |
|---|---|---|
| Trace pass: `scripts/find_syncs.py` | Every blocking CUDA call, host blocked time, GPU idle, op chain | Python lines |
| Stack pass: `scripts/sync_stacks/` | Python stack per sync, per step, per thread | Costs; syncs outside torch |
| `find_syncs.py --stacks` on the hooked run | Python site per trace sync point | Hook overhead inflates costs |
| `scripts/join_sync_dumps.py` | Python sites (hooked run) on costs (unhooked trace) | Needs identical sequences |

Start with the trace pass on an existing trace (no rerun). Rerun with the stack hooks only when you need lines,
then join the two. nsys was not needed here (`cuda_api_sum` would count the same runtime calls without
attribution); see `tools/nsight-systems.md` if you want it.

## 1. Trace pass

`python3 scripts/find_syncs.py trace_0.json.gz [--steps N] [--list] [--dump rows.json]` on a `torch.profiler`
chrome trace. The window is the last complete step, from one CPU-side `forward` annotation to the next, so
optimizer and logging syncs count. What it treats as blocking, checked against the event names in real traces:

- `cudaStreamSynchronize`, `cudaDeviceSynchronize`, `cudaEventSynchronize`, synchronous `cudaMemcpy*` (runtime
  `cat == "cuda_runtime"` and driver `cuda_driver` names).
- `cudaMemcpyAsync` whose host call returned after its GPU copy (matched by `args["correlation"]`) finished:
  `Memcpy DtoH (Device -> Pageable)`. `.item()`, `.tolist()`, `.cpu()` copy through `memcpy_and_sync`
  (`cudaMemcpyAsync` then `cudaStreamSynchronize`), and the wait lands in the memcpy. Grouping by innermost CPU op
  makes that pair one sync point.
- Not blocking: `cudaEventQuery` (polling, mostly the NCCL watchdog thread), `cudaStreamWaitEvent` (device-side),
  D2H into pinned memory with `non_blocking=True`.

Costs per sync point:
- **host**: blocked time in the calls. Hundreds of ms per step is normal when the host runs far ahead; it only
  costs step time when the GPU then waits for the host.
- **idle@ret**: the GPU idle gap (union of kernels, memcpys, memsets on all streams) containing the return.
- **exposed**: GPU idle from the drain before the return until the host is ahead again (first kernel launched
  after the return that starts more than 50 us after its launch call). After a sync the queue is empty, so the
  launch-bound gaps that follow belong to it; idle@ret misses those (e.g. the forward-to-backward transition).
- Check GPU busy % first. At 98% busy, syncs cannot buy much step time however many there are.

Attribution is the enclosing `cpu_op` chain on the calling thread plus the nearest `user_annotation`, found by
walking a parent array (not a fixed lookback: step-level annotations start thousands of ops earlier). Backward
syncs run on the autograd thread, which has its own `tid` and no `forward`/`backward` annotation. Common chains:

| Op chain | Usual source |
|---|---|
| `aten::item > aten::_local_scalar_dense` | `.item()`, `int(t)`, `float(t)`, f-string formatting of a tensor |
| `aten::is_nonzero > aten::item` | `if t:`, `bool(t)`, `assert t` |
| `aten::to > aten::_to_copy > aten::copy_` (D2H pageable) | `.tolist()`, `.cpu()` |
| `aten::to > aten::_to_copy > aten::copy_` (H2D, tiny) | `torch.tensor(python_scalar, device="cuda")` |
| `aten::index > aten::nonzero` | Boolean-mask indexing `x[mask]` |
| `IndexBackward0 > aten::_index_put_impl_ > aten::nonzero` | Backward of `x[mask]` |
| `aten::repeat_interleave > aten::item` | `repeat_interleave` without `output_size` (two syncs) |
| `<custom op> > aten::to > ... copy_` | A sync inside a `torch.library.custom_op`; the stack pass names the line |

## 2. Stack pass: Python file:line without editing the project

`scripts/sync_stacks/sitecustomize.py` is imported by every Python process that has its directory on
`PYTHONPATH`, so it reaches torchrun workers without touching the repo, venv, or launcher. It appends one JSON
line per sync (full Python stack, native thread id, wall time, step, autograd node in the autograd thread). Env vars
are in its docstring. Two sources, compared in a probe (`x` on GPU):

| Case | `set_sync_debug_mode("warn")` | GPU-trace sync callbacks |
|---|---|---|
| `.item()`, `bool(t)`, `.tolist()`, `.cpu()`, `nonzero`, `x[mask]`, `masked_select`, `unique` | yes | yes |
| `repeat_interleave` without `output_size` (two syncs), `Stream.synchronize()` | yes | yes |
| Pageable CPU tensor `.to("cuda")` | yes | yes |
| `torch.cuda.synchronize()`, `Event.synchronize()` | **no** | yes |
| `.to("cpu", non_blocking=True)`, copy into pinned with `non_blocking=True` | no (not a sync) | no |
| Sync in a Python `autograd.Function.backward` | yes, autograd thread | yes, autograd thread |
| Sync in a C++ autograd node (`IndexBackward0`) | replayed at `.backward()` | yes, no Python frames |

- **Warn mode** is the default. There is no env var for it in torch 2.13 (only the Python call). A warning is
  recorded when the Python-level call returns, so one call with two syncs gives two records after both.
- **Callbacks** (`SYNC_STACKS_CALLBACKS=1`, the CUDA sanitizer hooks) are more complete but activating GPU trace
  calls into Python on every allocation and event. In prime-rl SFT with selective activation checkpointing the
  first backward crashed (`cuda trace hook execution failed: SystemError` inside `torch/utils/checkpoint.py`
  `unpack_hook`). Use them only without activation checkpointing. Before the crash they did show 174
  `torch.cuda.synchronize()` calls from Triton autotuning in step 1, which warn mode never reports.
- Neither sees syncs outside torch's sync paths: NCCL, raw CUDA calls from extensions, library host code. The
  trace pass sees those; compare counts per step between the two passes.
- For a C++ autograd node, use the node name and the forward op of the same site (`IndexBackward0` of dims
  `[1, 32768]` is the backward of the `x[mask]` whose forward sync has the stack).
- Hook cost: the first version (`traceback.extract_stack` plus a flushed write per sync) added about 0.35 ms per
  sync with spikes to 9 ms, and exposed GPU idle went from 29 to 95 ms per step. The current version walks frames
  and flushes once per step: about 5 us per sync in a probe, not yet measured in a full run. Either way take costs
  from an unhooked trace.

### prime-rl recipe

Dry-run to write the resolved config, then launch it the way the rendered sbatch does, with the hook directory on
`PYTHONPATH` and the output directory outside the run directory (compile caches as in `projects/prime-rl.md`):

```bash
uv run sft @ cfg.toml --run.name $R --max-steps 5 --trace-path ~/tmp/profiling/<investigation>/traces/$R --dry-run
RUN=$PRL_OUTPUT_DIR/$R
PRL_ATTEMPT_CONFIG_DIR=$RUN/configs/attempt_1/resolved PRL_ATTEMPT_LOG_DIR=$RUN/logs/attempt_1 \
PYTHONPATH=<skill>/scripts/sync_stacks SYNC_STACKS_OUT=<existing dir> \
  uv run --no-sync sft @ $RUN/configs/attempt_1/resolved/sft.json --dry-run False
```

The resolved config keeps `dry_run = true`, hence the override. The default step hook,
`torch.cuda.reset_peak_memory_stats`, runs once at the top of each SFT and RL training step.

Then, with an unhooked trace of the same config (`unhooked.json.gz`):

```bash
python3 scripts/sync_stacks_report.py $SYNC_STACKS_OUT/syncs_rank0.jsonl
python3 scripts/find_syncs.py $RUN/traces/trace_0.json.gz --stacks $SYNC_STACKS_OUT/syncs_rank0.jsonl --dump hooked.json
python3 scripts/find_syncs.py unhooked.json.gz --dump unhooked.json
python3 scripts/join_sync_dumps.py unhooked.json hooked.json
```

`--stacks` matches records to trace sync points on the same thread in order (record wall time minus the trace's
`baseTimeNanoseconds`); it prints the match rate and records with no blocking call. The join requires equal
per-thread counts and reports op chain mismatches (0 of 121 here).

## Pitfalls

- Compare steps 3 to N-1: step 1 has compile and autotuning syncs, and the last step also covers post-loop work.
- Two `.tolist()` in a row: only the first waits (tens to hundreds of ms of host time), the second takes about
  20 us, yet the second often has more exposed idle, because the host then has to refill an empty queue.
- If the process crashes, loguru-style tracebacks that print tensor values add thousands of syncs to the record.
