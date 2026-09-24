# Trace figures for PRs

A figure is worth adding when the mechanism is visual: a removed compute gap, new overlap, fewer or shorter
kernels in a region.

## Timeline figure recipe

Models: prime-rl PR #3638's reduce-scatter overlap figure, and PR #3645's RoPE figure (the preferred layout:
two left-aligned timelines plus a per-category delta panel).
- One panel per arm, stacked, sharing a time axis in milliseconds.
- Rows per stream of interest (e.g. main-stream compute, a communication stream).
- Align both arms at the start of the region that changed, at t = 0, and mark where the region ends in each
  arm (see "What reads well").
- Color by category, label the key region inline, and annotate the saved time with an arrow and its size.
- The #3645 figure, as a starting point:

  ```bash
  uv run --script scripts/timeline_figure.py --out fig.png --window -2 100 \
    --anchor-annotation "FSDP::all_gather_copy_out (model.layers.2)" \
    --end-annotation "FSDP::all_gather_copy_out (model.layers.2._checkpoint_wrapped_module.mlp.router)" \
    --region-label "attention block" --anchor-label "the start of layer 2's forward, rank 0" \
    --trace "Before: main (<sha>)=<before>/trace_0.json.gz" --trace "After: this PR (<sha>)=<after>/trace_0.json.gz" \
    --category "torch.cat:CatArrayBatchedCopy:#d55e00" --category "fused RoPE kernel:^_mla_rope:#009e73" \
    --category "GEMM:^nvjet|^(?!.*rmsnorm).*cutlass:#0072b2" --category "elementwise / copy:elementwise|copy|Functor:#e69f00" \
    --title "<model>, <scale and shared settings>, rank 0, main GPU stream"
  ```
- Title states model, scale, and the setting shared by both arms; each panel's subtitle states the arm and
  its headline metric.
- The x-axis label names the anchor, rank, and step.
- For host stalls lasting seconds (JIT recompiles, syncs): align at the step start (`timeline_figure.py`
  without `--anchor`; `--step-index` picks a step that stalls in one arm only), window the whole step, and
  shade idle gaps with `--annotate-gaps`, which names the CPU op the host was inside. Back the cause with
  evidence outside the trace (e.g. compile-cache file mtimes vs step end times).

## What reads well (user feedback, 2026-09-24)

- The per-category delta bar panel (after minus before, main-stream kernel time per step) is the most
  readable part: keep it by default (see "Embedding in a PR" for when to caveat or drop it).
- Align timelines at the start of a region (e.g. `--anchor-annotation "FSDP::all_gather_copy_out
  (model.layers.N)"` for a layer's forward) with a window starting near 0, so every arm is left-aligned and
  the saving shows as a shorter bar. Mark the region's end with `--end-annotation` (e.g. the layer's
  `mlp.router` copy-out ends its attention block) to get per-arm lengths and a difference arrow.
- Don't align at a kernel inside the region (e.g. the attention kernel): the axis runs negative and the
  saving shows up as a ragged left edge, which confused the reader.

## Supporting table

Put untraced timing (median, min/max) next to the figure, plus per-category kernel-time deltas from the
trace. The figure explains the mechanism; the untraced numbers are the claim.

## Embedding in a PR

- Add the PNG to the PR branch in its own commit, then remove it in the next commit, so a squash merge
  leaves it out of `main`. Reference it by a raw GitHub URL pinned to the adding commit's full SHA, as #3638
  did: `https://raw.githubusercontent.com/<org>/<repo>/<sha>/<path>.png`. No manual upload step for the user,
  and no amending (the URL stays valid as long as the adding commit is in the pushed history).
- GitHub renders only images hosted on GitHub, so the image shows once those commits are pushed. Pushing
  needs the user's explicit approval; until then, write the URL into `PR.md` and say it goes live on push.
- Don't let a figure mislead. If the delta panel shows a per-rank effect that does not reach step time (e.g.
  under context parallelism, rank 0 saves kernel time while the slowest rank sets the step), usually keep it
  and say so in the caption; drop it (`--no-delta`) only when it is really non-representative of the change.
- Link the exact before and after commits, and the config used, as GitHub URLs.
- Caption: start it with `**Figure:**` and say what the panels plot (stream, rank, step, run scale and
  settings), what the arms are aligned at and what any marker lines mean, what changed and by how much,
  what the delta panel sums over, and that the profiled run explains the mechanism while unprofiled runs
  carry the timing claim.
