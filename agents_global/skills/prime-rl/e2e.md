# End-to-end A/B tests for prime-rl trainer changes

Before launching, post the run matrix as a Cartesian product (workloads x arms x layouts, plus repeats and
traces) and confirm it with the user. Say which cells you drop and why.

## Workloads

Run both unless the change only touches one of them:
- **Qwen3-30B-A3B**, fake data with `model.debug.force_balanced_routing`: a steady MoE perf proxy.
- **GLM-4.5-Air**, truncated with `model.debug.num_layers` (propose a count that fits the change, e.g. a
  deeper truncation for perf than for parity, and let the user override it), on real SFT data
  (`PrimeIntellect/INTELLECT-3-SFT-10K`, renderer `glm-4.5`): real routing and real documents.

## Run hygiene

- **No offloading, set explicitly:** `model.optim_cpu_offload = false` (defaults to true),
  `model.ac_offloading = None` (on by default), `model.fsdp_cpu_offload = false`. Offloading adds host and
  copy-stream work that confounds timing.
- **No checkpoints:** leave `[ckpt]` unset. Saves add I/O to step time and fill disk.
- **About 20 steps per run:** enough for a steady state after compile warmup. Take medians over the steps
  after warmup.
- **Set `model.ep` explicitly:** `"auto"` resolves to the world size. Default to the expert parallelism used
  in practice, not ep=1.
- **Same hardware for every arm:** prefer one exclusive node running all arms serially over parallel jobs on
  different nodes.
- **Frozen arms:** give each arm its own worktree, checked out detached at the commit under test (base at its
  SHA, feature branch at its SHA), with fresh compile caches per run. Never run an arm from a worktree that is
  still being edited or pulled. Record the commits in the results.
- **Noise floor:** repeat the baseline and the leading candidate with identical code. Parity means within that
  floor, and a real bug shows as a gap that grows over steps.

## Reporting

Median step time with min and max over steady-state steps, MFU, throughput per GPU, peak memory, and per-step
loss and grad norm from `monitors/file/metrics.jsonl`. For why one arm is faster, use the `profiling` skill.
