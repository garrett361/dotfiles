---
name: profiling
description: Measure and explain GPU/PyTorch performance and A/B a change fairly, with hard evidence (numbers plus trace figures). Use when benchmarking a kernel, op or PR; asking why a speedup misses end to end or where step time goes; profiling a training run (torch.profiler, Nsight Systems, Nsight Compute); finding host syncs or torch.compile recompiles; inspecting kernel stalls, SASS or spills; viewing a trace in Perfetto; or producing perf evidence for a PR.
---

# Profiling

## Rule: everything goes through this skill's scripts

Every analysis, table, merged trace, and figure comes from running a script in this skill's `scripts/` with
explicit arguments: no inline `python -c`, no heredoc analysis, no scratch scripts in `~/tmp`, no hand-edited
traces or figures. Every number and figure must be regenerable from the raw traces and the investigation's
`commands.sh`, which records each command that produced a result, in order, with all arguments. Files a
script takes as input (a `bench_ops.py` cases file, a toy repro) are not analysis; keep them in the
investigation's `inputs/`.

When a script can't do what's needed, extend it (or add one), run it, and route to it from this file or the doc
that covers its question. Keep extensions general and backward compatible: a flag with a sensible default,
documented in the script's usage docstring, never hardcoded to one model, run, or kernel. Project-specific
knowledge goes in arguments or `projects/<repo>.md`. Capture harnesses that run inside a project (e.g. a
`sitecustomize.py` hook) also live in `scripts/`.

## 1. Pick the tool by the question

Read only what the matching line names. A script named without a doc is documented by its module docstring at the top of
the file. Run each script as its docstring says: `uv run --script` by default (each file's header declares its
dependencies), and the project's interpreter (`uv run --no-sync python`) for the few that import torch or the project
(`bench_ops.py`, `prime_rl_logprob_ab.py`).

Op level:
- Is this op faster, and by how much (median, p20, p80, peak memory, output check)? `scripts/bench_ops.py`
  (`--cudagraph` for ops under ~20 us); `tools/do-bench.md`.
- How long does a region of my code take, per call? Copy `scripts/cuda_timer.py` into the project (the one script
  meant to be copied, not run).
- Which kernels inside an op cost the time? `bench_ops.py --trace`, then `scripts/top_kernels.py --whole-trace
  --decimals 3` and `scripts/kernel_diff.py --decimals 3`.
- A CuTe DSL op: does it re-trace or pay host overhead on every call? `tools/cute-dsl.md`, before timing it.

End to end, from traces:
- Why doesn't an op win show up in step time? Capture both arms (`tools/torch-profiler.md`), then diff them with
  the scripts below.
- Where should I optimize, which kernels cost most and which op launched them? `scripts/top_kernels.py` (torch
  trace) or `scripts/nsys_kernels.py` (nsys SQLite); `analysis/top-kernels.md`.
- Which kernels changed between two traces, per kernel, category or launching op? `scripts/kernel_diff.py`.
- Where does the step time go (compute by category, exposed comm, idle by cause), and why is arm B slower,
  reconciled with untraced step time? `scripts/step_accounting.py`, then `scripts/accounting_figure.py`.
- How much host work (launches, thread busy time, named ops) does each arm issue per step? `scripts/host_ops.py`.
- Do host-side stream waits (e.g. FSDP's reduce-scatter cap) stall the GPU, and how much does labeled
  communication overlap compute? `scripts/comm_waits.py`, figure via `scripts/timeline_figure.py --comm-kernel`.
- What annotations and host ranges does a trace have; where does one op's host time go, down to Python frames?
  `scripts/trace_events.py` (`--include-python` on a `with_stack=True` trace).
- Host gaps, stream overlap and NCCL across a whole step, with no code change? `tools/nsight-systems.md`.

Runs, host and compiler:
- How do arms compare on step time, memory, loss (prime-rl run dirs or any `.jsonl` with a step key)?
  `scripts/run_metrics.py`.
- Where does the host block on the GPU (syncs), from which Python line? `scripts/find_syncs.py` (costs), then
  `scripts/sync_stacks/`, `sync_stacks_report.py` (file:line) and `join_sync_dumps.py`; `analysis/cuda-syncs.md`.
- What keeps `torch.compile` recompiling, at which step? `scripts/recompile_reasons.py`.
- Does a prime-rl model change move logprobs, step time or peak memory on real weights, and which class did a
  module become? `scripts/prime_rl_logprob_ab.py`.

Inside one kernel:
- Why is it slow (bandwidth, latency stalls, occupancy), and which source lines do warps stall on?
  `tools/nsight-compute.md` (`scripts/ncu_source_lines.py`).
- A CuTe DSL kernel: JIT cache, PTX/SASS dumps, registers, spills? `tools/cute-dsl.md`.
- Do two kernels (TileLang, CuTe DSL, Triton, CUDA) share a design: MMA, TMA vs `cp.async`, barriers,
  registers, spills by source line? `scripts/sass_inventory.py` (multi-arch `.so` tables are per SASS arch; pass
  `--kernel` on large caches).
- When does each warp role issue, wait and finish, and which wait gates the next step? `tools/intra-kernel.md`
  (`intra_kernel_events.py`, `intra_kernel_intervals.py`, `intra_kernel_ab_figure.py`).

Showing results:
- A before/after timeline figure: `scripts/timeline_figure.py`; `reporting/figures.md`.
- The user views a remote trace locally (one step via `scripts/trim_last_step.py`, or arms side by side via
  `scripts/merge_traces.py`): `viewing/remote-perfetto.md`.

Project-specific capture recipes live in `projects/` (e.g. `projects/prime-rl.md`). Read the one for the
current repo before launching anything. Without one, capture as in `tools/torch-profiler.md` and pass the
repo's step annotation and optimizer kernel to the scripts' step flags (`--annotation`, `--step-marker`,
`--step-boundary`), whose defaults, where they have one, follow prime-rl. A `torch.profiler.schedule` capture
names each step `ProfilerStep#<n>`, which the scripts match as `ProfilerStep`; for `top_kernels.py` prefer
`--launched-in ProfilerStep`, since CPU-timed windows misplace kernels when the GPU lags the host.

## Where artifacts go

One root per investigation, `~/tmp/profiling/<investigation>/` (e.g. `ds-v4-rope`):

| Path | Contents |
|---|---|
| `traces/<run>/` | Raw per-rank traces; point the capture here (e.g. prime-rl `--trace-path`) |
| `derived/` | Trimmed and merged traces, kernel tables, CSVs, nsys reports and exports |
| `figures/` | Rendered figures |
| `inputs/` | Files scripts take as input: cases files, toy repros |
| `serve/` | Symlinks to what the user views in Perfetto; the CORS server is rooted here |
| `commands.sh` | Every skill-script invocation that produced a result, in order, with all arguments |
| `NOTES.md` | Index: each run's name, job, commit, config, and what each file is |

Per-run compile caches go in `~/tmp/profiling/caches/<run>/` (node-local ones in `/tmp/$USER/<run>/`). Timing
metrics stay where the tool writes them (e.g. the prime-rl run dir); don't move or delete those.

Cleanup, when the user says an investigation is done: report `du -sh` per path and propose deletions; delete
only with approval. Usually safe: other ranks' raw traces, nsys `.sqlite` exports (regenerable from
`.nsys-rep`), decompressed copies of `.json.gz`, filled compile caches. Keep rank-0 raw traces, `derived/`,
`figures/` and `NOTES.md` until the PR merges.

## 2. Work in layers, diff arms at every layer

1. **Op timing**: fast to iterate, but only covers the code you chose to include.
2. **Op kernel breakdown**: shows which kernels inside the op changed (casts vs GEMMs, launch counts).
3. **End-to-end trace diff**: the only layer that catches costs in code the op benchmark never runs.

An op-level win that disappears end to end is a finding, not noise: go to layer 3 and find what cancels it.

## 3. A/B hygiene

- Freeze each arm's code in its own worktree or commit; never time against a tree you are editing.
- Identical config, data, seed, step count, and rank for every arm. Change one thing.
- Fresh compile caches per arm (`TRITON_CACHE_DIR`, `TORCHINDUCTOR_CACHE_DIR`, `TILELANG_CACHE_DIR`,
  `CUTE_DSL_CACHE_DIR`), or JIT warmth biases the comparison.
- Time ops and regions with CUDA events (`bench_ops.py`, `cuda_timer.py`), never host clocks around
  `torch.cuda.synchronize()`. Events also count idle gaps while the host is still launching, so a host-bound
  region reads as host time. Step time comes from untraced runs (median over steady-state steps); traces are
  for attribution only, since profiler overhead changes step time.
- Validate numerics before timing: bitwise (`torch.equal`, which compares fp8 directly in torch 2.13) when the change
  should be exact, otherwise loss/grad-norm curves that track step by step.
- Run arms on the same hardware class, serially or in parallel as the user asks (ask if unclear); never
  share GPUs between a timing run and anything else.

## 4. Report hard evidence

- A results table with medians, spread (min/max), and the exact configs and commits of both arms.
- An ASCII diagram of what differs between the arms: `reporting/ascii-diagrams.md`.
- A trace figure when the mechanism is visual (a removed gap, new overlap): `reporting/figures.md`.
- Say what was measured where: scaled-down proxy vs full model, traced vs untraced, which rank and step.
- Single runs are single runs; say so rather than implying statistics you did not collect.
