---
name: profiling
description: Measure and explain GPU/PyTorch performance with the right tool for the question (triton do_bench, torch.profiler traces, Nsight Systems, Nsight Compute), A/B a change fairly, and report hard evidence (numbers plus trace figures). Use when benchmarking a kernel or PR, asking why a speedup does or does not show up end to end, profiling a training run, or producing perf evidence for a PR description.
---

# Profiling

## Rule: everything goes through this skill's scripts

Every analysis, table, merged trace, and figure is produced by running a script in this skill's `scripts/`
with explicit arguments. No ad hoc code: no inline `python -c`, no heredoc analysis, no scratch scripts in
`~/tmp`, no hand-edited trace files or figures. The goal is that every number and figure can be regenerated
later, by anyone, from the recorded commands and the raw traces.

The scripts are meant to grow: when one can't do what's needed, extend it (or add a new script) as part of
the investigation, then run it. Agents are expected to do this, and to update this file and the docs it links
when they add a capability. Keep extensions general and maintainable: a new flag or option with a sensible
default, documented in the script's usage docstring, not hardcoded to one model, run, or kernel name.
Project-specific knowledge goes in arguments or in `projects/<repo>.md`, not in the script. Keep extensions
backward compatible so earlier recorded commands still reproduce.

Record every command that produced a result in the investigation's `commands.sh` (see below), in order,
with the script's path and all arguments. Capture harnesses that must run inside a project (e.g. a
`sitecustomize.py` hook) also live in this skill's `scripts/`, not in the investigation directory.

## 1. Pick the tool by the question

| Question | Tool | Details |
|---|---|---|
| Is this kernel/op faster, and by how much? | `triton.testing.do_bench` or CUDA events | `tools/do-bench.md` |
| How long does a region of my code take (per call, aggregated)? | `scripts/cuda_timer.py`, copied in | `tools/do-bench.md` |
| Which kernels inside an op cost the time? | `torch.profiler` over a few op iterations | `tools/torch-profiler.md` |
| Why doesn't an op win show up in step time? | Diff of two end-to-end `torch.profiler` traces | `tools/torch-profiler.md` |
| What annotations and host ranges does this trace have? | `scripts/trace_events.py` | its usage docstring |
| What keeps `torch.compile` recompiling, at which step? | `scripts/recompile_reasons.py` on a `TORCH_LOGS=recompiles` log | its usage docstring |
| Where should I optimize? Which kernels cost most? | `scripts/top_kernels.py` or nsys | `analysis/top-kernels.md` |
| How do arms compare on step time, memory, loss? | `scripts/run_metrics.py` (`--summarize`, `--lines`, bars) | its usage docstring |
| Where are host gaps, syncs, stream overlap? | Nsight Systems | `tools/nsight-systems.md` |
| Where does the host block on the GPU (syncs), from which line? | `scripts/find_syncs.py` | `analysis/cuda-syncs.md` |
| Why is one kernel slow (bandwidth, occupancy)? | Nsight Compute | `tools/nsight-compute.md` |
| How does the user see a remote trace locally? | Perfetto UI + ssh forward (`serve_cors.py`; big traces: `serve_trace_processor.py`) | `viewing/remote-perfetto.md` |

Project-specific capture recipes live in `projects/` (e.g. `projects/prime-rl.md`). Read the one for the
current repo before launching anything.

Always time GPU work with CUDA events, never host clocks around `torch.cuda.synchronize()`: events measure the
stream without stalling the host. For timing a region inside a project, copy `scripts/cuda_timer.py` (one file,
no dependencies beyond torch) into it rather than hand-rolling event pairs; it is the one script meant to be copied
instead of run.

## Where artifacts go

One root per investigation, `~/tmp/profiling/<investigation>/` (e.g. `ds-v4-rope`):

| Path | Contents |
|---|---|
| `traces/<run>/` | Raw per-rank traces; point the capture here (e.g. prime-rl `--trace-path`) |
| `derived/` | Trimmed and merged traces, kernel tables, CSVs, nsys reports and exports |
| `figures/` | Rendered figures |
| `serve/` | Symlinks to what the user views in Perfetto; the CORS server is rooted here |
| `commands.sh` | Every skill-script invocation that produced a result, in order, with all arguments |
| `NOTES.md` | Index: each run's name, job, commit, config, and what each file is |

Per-run compile caches go in `~/tmp/profiling/caches/<run>/` (node-local ones in `/tmp/$USER/<run>/`). Timing
metrics stay where the tool writes them (e.g. the prime-rl run dir); don't move or delete those.

Cleanup, when the user says an investigation is done or disk use grows: report `du -sh` per path and propose
deletions, but delete only with the user's approval. Usually safe to drop: raw traces of ranks other than the
analyzed ones, nsys `.sqlite` exports (regenerable from `.nsys-rep`), decompressed copies of `.json.gz`,
and compile caches (after confirming they filled). Keep rank-0 raw traces, `derived/`, `figures/`, and
`NOTES.md` until the PR merges. Stop any server by its saved PID.

## 2. Work in layers, diff arms at every layer

1. **Op timing**: fast to iterate, but only covers the code you chose to include.
2. **Op kernel breakdown**: shows which kernels inside the op changed (casts vs GEMMs, launch counts).
3. **End-to-end trace diff**: the only layer that catches costs in code the op benchmark never runs.

An op-level win that disappears end to end is a finding, not noise: go to layer 3 and find what cancels it.

## 3. A/B hygiene

- Freeze each arm's code in its own worktree or commit; never time against a tree you are editing.
- Identical config, data, seed, step count, and rank for every arm. Change one thing.
- Fresh compile caches per arm (Triton, Inductor, TileLang, etc.), or JIT warmth biases the comparison.
- Timing comes from untraced runs (median over steady-state steps). Traces are for attribution only:
  profiler overhead changes step time.
- Validate numerics before timing: bitwise (`torch.equal`, fp8 via `.view(torch.uint8)`) when the change
  should be exact, otherwise loss/grad-norm curves that track step by step.
- Run arms on the same hardware class, serially or in parallel as the user asks (ask if unclear); never
  share GPUs between a timing run and anything else.

## 4. Report hard evidence

- A results table with medians, spread (min/max), and the exact configs and commits of both arms.
- A figure from the traces when the mechanism is visual (a removed gap, new overlap): left-aligned
  before/after timelines of the changed region plus a per-category delta panel, with a short `**Figure:**`
  caption (one or two plain sentences: what it shows and the takeaway) and embedded by a pinned raw GitHub
  URL. See `reporting/figures.md`.
- Delta panel: keep the per-category delta panel by default; if it could mislead (e.g. a per-rank saving that does not
  reach step time), say so in the caption, and drop it only when it is really non-representative.
- Say what was measured where: scaled-down proxy vs full model, traced vs untraced, which rank and step.
- Single runs are single runs; say so rather than implying statistics you did not collect.
