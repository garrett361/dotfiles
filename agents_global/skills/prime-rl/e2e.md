# End-to-end A/B tests for prime-rl trainer changes

Before launching, post the run matrix as a Cartesian product (workloads x arms x layouts, plus repeats and
traces) and confirm it with the user. Say which cells you drop and why.

## Workloads

Run both unless the change only touches one of them:
- **Qwen3-30B-A3B**, fake data with `model.debug.force_balanced_routing`: a steady MoE perf proxy.
- **GLM-4.5-Air**, truncated with `model.debug.num_layers` (propose a count that fits the change, e.g. a
  deeper truncation for perf than for parity, and let the user override it), on real SFT data
  (`PrimeIntellect/INTELLECT-3-SFT-10K`, renderer `glm-4.5`): real routing and real documents.

## Compile-path changes: add a CP arm on dynamic lengths

A change that makes more code compile (removes a graph break, edits a custom op fake, changes the compile
layout) can expose recompiles that the old graph break hid. Context parallelism is the known trap: its
attention parameters (`max_seqlen_k`, `cu_seqlens`) change with every packed document layout.

- Add an arm with `model.cp = 2` on the GLM-4.5-Air real-data workload, `fullgraph = false`, against main. Real
  variable-length documents are required: fake data with fixed length (one document per row) never changes
  the CP parameters, and toy models hit the recompile limit within a few steps and fall back to eager.
- Report per-rank recompile counts, CP guard failures and the per-step time series. A recompile storm shows as
  slow steps (the max), not in the median.
- State in the PR whether CP users are safe, or which PR must land first.

Seen in prime-rl #4086: 14 to 25% faster at cp=1, but 42 to 55 s per step against 3.6 s on main at cp=2 until
#4068 (CP parameters as forward args) was underneath.

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
- **Harness in history:** commit the A/B configs, drivers and comparison scripts per the rule in `SKILL.md`.
- **Noise floor:** repeat the baseline and the leading candidate with identical code. Parity means within that
  floor, and a real bug shows as a gap that grows over steps.

## Reporting

Median step time with min and max over steady-state steps, MFU, throughput per GPU, peak memory, and per-step
loss and grad norm from `monitors/file/metrics.jsonl`. For why one arm is faster, use the `profiling` skill.
