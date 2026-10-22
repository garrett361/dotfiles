# dist_moe (`meta-pytorch/dist_moe`)

Verified 2026-10-21 on B300 SXM6 (sm_103a), `nvidia-cutlass-dsl` 4.8.0, torch 2.14.1+cu130, Triton 3.8.0, at
dist_moe `caf454c` plus the `feat/swiglu-beta` branch.

## Setup

- No in-repo benchmark scripts. Time `dist_moe.routed_experts` forward plus backward through `scripts/bench_ops.py`
  with a cases file; a fake single-rank group (`dist.init_process_group(backend="fake", store=dist.HashStore(),
  rank=0, world_size=1)` after `import torch.testing._internal.distributed.fake_pg`) runs every pipeline (BF16,
  MXFP8 staged and Mega, NVFP4 inference) on one GPU. Example: `~/tmp/profiling/dist-moe-swiglu-beta/inputs/cases.py`.
- Venv: `uv venv --python 3.12 && uv pip install --torch-backend=cu130 -e . pytest ruff`. For SASS dumps also
  `uv pip install nvidia-cuda-nvdisasm` (`../kernels/cute-dsl/authoring.md`).
- Two-rank tests (`DistMoeTwoRankTest`) need two GPUs visible; `pytest -k` selects them as usual.

## Compile caching and names

- CuTe kernels are compiled with explicit `cute.compile` and kept in in-process dicts (`_COMPILED_CACHE` /
  `_compile_or_get` in `dist_moe/kernels/blockscaled_grouped_gemm.py`, `jit_cache` on the quantize kernels'
  `compile` methods), so every new process recompiles; warm up inside the benchmark process.
- Kernel names carry a `_cute_` prefix set by `scoped_kernel_name_prefixes` (`dist_moe/kernels/_kernel_name_prefix.py`),
  e.g. `_cute_quantize_<producer>_<dtype>_<format>_...`, so `ncu -k regex:_cute_` selects them. Clamped-SwiGLU
  quantize kernels append `_clamp<alpha hex>_<limit hex>` (and `_beta<hex>` when beta is not 1.0).
- Compile options are per launcher: `--opt-level=1 --ptxas-options='--Ofast-compile=min'` on some block-scaled
  dispatch kernels, `--opt-level=1` on Mega, and a `CUTE_DSL_OPT_LEVEL` key (1 or 3) in the chunked-Mega kernel
  config dict. These change codegen, so hold them fixed across arms.
- Triton kernels are named `_triton_*`.

## Annotations

- `record_function` ranges: `dist_moe_forward`, `dist_moe_backward`, `dist_moe_preprocess`, `dist_moe_recompute`,
  `dist_moe_routing` (BF16, `api.py`) and `moe_forward_main`, `moe_forward_plan`, `moe_forward_recompute`,
  `moe_backward_main`, `moe_backward_plan`, `moe_backward_preprocess`, `moe_backward_postprocess`,
  `moe_dispatch_routing`, `moe_preprocess`, `moe_postprocess` (block-scaled, `_blockscaled.py`).
- In-kernel event tracing (IKET) goes through `dist_moe/kernels/_iket_shim.py`; instrumentation levels are
  trace-time constants invisible to the DSL disk cache key, so run instrumented workloads with caching off.

## Checking that a change leaves kernels untouched

- Run the same seeded pipelines from two worktrees with `PYTHONPATH=<tree>` (it overrides the editable install),
  `CUTE_DSL_KEEP=sass CUTE_DSL_DUMP_DIR=<arm>/sass TRITON_CACHE_DIR=<arm>/triton`, save outputs and gradients, and
  compare with `torch.equal`; then `scripts/artifact_diff.py <arm A> <arm B>`. Mind the one-dump-per-class-name
  overwrite in `../kernels/cute-dsl/authoring.md`.
