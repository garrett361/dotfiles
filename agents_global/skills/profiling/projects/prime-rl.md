# prime-rl

## Capturing traces in SFT

- `uv run sft @ <config> --trace-path ~/tmp/profiling/<investigation>/traces/<run> --max-steps 5` wraps the whole training loop in
  `torch.profiler` (CPU and CUDA, `record_shapes`) and writes `trace_<rank>.json.gz` per rank. A config
  validator rejects `max_steps >= 10` when tracing.
- The trace includes compile-heavy step 1. Analyze the last step only. The loop's `forward` annotations
  appear twice per step (the CPU `user_annotation` and its GPU-stream projection), so select the last
  CPU-side one (`cat == "user_annotation"`); `scripts/trim_last_step.py` does this.
- Per-step timing without the profiler: `<run dir>/monitors/file/metrics.jsonl`, merge records by `step`,
  take the median `time/step` over steady-state steps.
- Without `[slurm]`, `uv run sft` runs single-node locally under torchrun, so it can run inside an `srun`/`sbatch`
  allocation. To inject code into the trainer processes without editing the repo (e.g. the sync-stack hooks), put
  a `sitecustomize.py` directory on `PYTHONPATH`; `analysis/cuda-syncs.md` has the tested recipe.

## Proxy for profiling, full model for timing

- For DeepSeek V4 Flash, a one-node run with 6 layers (`model.debug.num_layers = 6`), cp 8, ep 8, the same
  sequence length, and batch 1 matches the per-GPU tokens of the 8-node full-model run. It reproduced the
  8-node MFU in a prior investigation. Re-check the before/after step-time ratio against full-model untraced
  runs before trusting its traces.
- Keep full-model untraced runs as the timing claim.

## Launching on Slurm

- `uv run sft ... --dry-run` renders `<run dir>/launcher/sft.sbatch` and the resolved config
  (`<run dir>/configs/attempt_1/resolved/sft.json`). Check the resolved config, then `sbatch --parsable`
  the script, chaining arms with `--dependency=afterany:<job>` to run them serially.
- `slurm.project_dir` defaults to the launch directory, so the arm's code is whatever worktree you launch
  from. Launch each arm from its own worktree, with submodules at their recorded commits and a venv built by
  `uv sync --all-extras --all-packages`.
- Single-node configs need `--slurm.partition <p>` (and a job name) to go through Slurm.

## Fresh compile caches per arm

sbatch exports the submitting environment, so set per-run caches at submit time:
`TILELANG_CACHE_DIR=~/tmp/profiling/caches/<run>/tilelang`, `TRITON_CACHE_DIR=/tmp/$USER/<run>/triton`,
`TORCHINDUCTOR_CACHE_DIR=/tmp/$USER/<run>/inductor`. Keep them outside the run directory: single-node jobs
re-run the run-directory check, which rejects anything the launcher did not write. TileLang's default cache
(`~/.tilelang/cache`) is shared across nodes and runs.

## Gotchas

- Jobs run `uv sync` at start and can fail on transient GitHub errors fetching wheels; resubmit.
- Fake data with `length = "fixed"` is one full-length document per row, so document-boundary code paths
  only see one case; use real packed data when they matter.
