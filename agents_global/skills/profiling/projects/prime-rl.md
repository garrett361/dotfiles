# prime-rl

## Capturing traces in SFT

- `uv run sft @ <config> --trace-path ~/tmp/profiling/<investigation>/traces/<run> --max-steps 5` wraps the whole training loop in
  `torch.profiler` (CPU and CUDA, `record_shapes`) and writes `trace_<rank>.json.gz` per rank. A config
  validator requires `max_steps` and rejects `max_steps >= 10` when tracing.
- The trace includes compile-heavy step 1. Analyze the last step only. The loop wraps each micro-batch's forward
  in `record_function("forward")`, so a step has K CPU-side `forward` annotations (`cat == "user_annotation"`,
  each also projected onto the GPU stream), where K = `data.batch_size * model.cp / (world size *
  data.micro_batch_size)`. `scripts/trim_last_step.py` and `top_kernels.py`'s default window start at the last
  one, which is the last step only when K = 1; otherwise `top_kernels.py --annotation-index -K --annotation-span K`
  covers the last whole step (with K = 2, a 720 ms window for a logged `time/step` of 0.72 s).
- Per-step timing without the profiler: `<run dir>/monitors/file/metrics.jsonl`, merge records by `step`,
  take the median `time/step` (and `perf/peak_memory`, GiB) over steady-state steps; `scripts/run_metrics.py
  --summarize` does this per run.
- Trainer logs of the ranks in `log.ranks_filter` (default `[0]`), lines prefixed `[trainer<rank>]:`, are in
  `<run dir>/logs/attempt_<N>/trainer.log`; every rank's own stdout/stderr is under `trainer/torchrun/` there. The
  launch environment reaches the trainer, so `TORCH_LOGS=recompiles uv run sft ...` works with
  `scripts/recompile_reasons.py <log> --rank 0 --step-regex 'Step (\d+) \|'`.
- Without `[slurm]`, `uv run sft` runs single-node locally under torchrun, so it can run inside an `srun`/`sbatch`
  allocation. To inject code into the trainer processes without editing the repo (e.g. the sync-stack hooks), put
  a `sitecustomize.py` directory on `PYTHONPATH`; `analysis/cuda-syncs.md` has the tested recipe.

## Logprob, step time and peak memory A/B

`scripts/prime_rl_logprob_ab.py` (usage in its docstring) answers "does my model change move per-token
logprobs, step time or peak memory?" without the full trainer: `dump` per arm, then `compare`, or `table` for
a PR. Its steps have no optimizer, so take full-step timing claims from SFT runs.

- Run both arms with the same world size and `--tokens-per-gpu`. The default `--text-glob` is relative to the
  working directory, so launch from the arm's worktree or pass an absolute glob.
- Dump the reference arm twice: the rerun is the noise floor. On one H200 (Qwen3-0.6B, 2048 tokens) a rerun
  was bitwise identical (`0 differ`), so any differing token is a real effect there; `--no-compile` moved
  1960 of 2048 tokens (mean |d| 0.031) and `--optimization-dtype bfloat16` moved none while cutting peak
  allocated memory from 5.08 to 3.44 GiB.

## Proxy for profiling, full model for timing

- For DeepSeek V4 Flash, a one-node run with 6 layers (`model.debug.num_layers = 6`), cp 8, ep 8, the same
  sequence length, and batch 1 matches the per-GPU tokens of the 8-node full-model run. It reproduced the
  8-node MFU in a prior investigation. Re-check the before/after step-time ratio against full-model untraced
  runs before trusting its traces.
- Keep full-model untraced runs as the timing claim.
- Its first 6 layers are sliding, sliding, CSA, HCA, CSA, HCA (`compress_ratios` 0, 0, 4, 128, 4, 128 in
  the DeepSeek-V4-Flash-0731 `config.json`), so the proxy exercises all three attention layer types.

## Launching on Slurm

- `uv run sft ... --dry-run` renders `<run dir>/launcher/sft.sbatch` and the resolved config
  (`<run dir>/configs/attempt_1/resolved/sft.json`). Check the resolved config, then `sbatch --parsable`
  the script, chaining arms with `--dependency=afterany:<job>` to run them serially.
- `slurm.project_dir` defaults to the launch directory, so the arm's code is whatever worktree you launch
  from. Launch each arm from its own worktree, with submodules at their recorded commits and a venv built by
  `uv sync --all-extras --all-packages`.
- Any `--slurm.*` flag sends a single-node config through Slurm; pass `--slurm.partition <p>`, since it
  defaults to `cluster` (the job name defaults to `prime-rl`). The script uses `output_dir` verbatim after
  `cd $PROJECT_DIR`, so pass an absolute `--output-dir` if you launch from elsewhere.

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
