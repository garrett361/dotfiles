# CuTe DSL kernels (`cutlass.cute`): compile vs launch

Status: verified 2026-10-10 on an H200 (sm90a) with `nvidia-cutlass-dsl` 4.7.1 (prime-rl venv), SLURM
job 3569. Read the docs at the installed version: `git -C ~/github/NVIDIA/cutlass show v4.7.1:media/docs/pythonDSL/...`.
The working-tree docs may describe a newer release.

## Time compile and launch separately

- `cute.compile(fn, *args)` returns an executor and always compiles: it neither reads nor fills the
  DSL's cache. Cache the executor yourself, keyed by whatever is static.
- Calling the `@cute.jit` function directly re-traces the Python on every call to compute the cache key
  (a hash of the traced IR): about 7 ms per call for a trivial kernel, before the in-memory cache hit.
  Never time, or ship, the implicit call path.
- Host overhead per call, trivial kernel: TVM-FFI executor (`options="--enable-tvm-ffi"`, `torch.Tensor`
  arguments, `make_fake_stream(use_tvm_ffi_env_stream=True)`) 4.0 us, classic executor with pre-converted
  `cute.Tensor` arguments 9.5 us, classic with `from_dlpack` per call 23.5 us. Benchmark the TVM-FFI
  executor, or report which path was timed.
- Compile cost: `import cutlass.cute` 0.6 to 4 s (15.6 s on the first process on a node), a trivial kernel
  0.1 s, a kernel with 4096 unrolled FMAs 7 s. `CUTE_DSL_JIT_TIME_PROFILING=1 CUTE_DSL_LOG_TO_CONSOLE=1
  CUTE_DSL_LOG_LEVEL=20` logs the split: tracing (`build_ir_module`), lowering plus ptxas
  (`compile_and_jit`), module load (`lookup`).
- To check that a kernel does not recompile per shape, compile once against fake tensors with symbolic
  sizes (`cute.sym_int()`, `make_fake_compact_tensor`) and call the one executor with several shapes.
- `make_fake_compact_tensor` defaults to mode 0 innermost (column-major). For torch's row-major tensors
  pass `stride_order=(rank-1, ..., 0)`. The TVM-FFI call checks only the static strides: dynamic ones are
  taken from the tensor at call time, so a wrong order surfaced only when a size-1 batch became 2
  ("Mismatched ...strides[0] ..., expected to be 1") and ran silently before.
- A real kernel for scale: the DSv4 sparse attention forward (2 WGMMA GEMMs, 36 `HGMMA`, 196 registers)
  compiles in 1.3 s (2.4 s with line info and dumps). `cute.compile` writes no file cache, so every new
  process pays that again.
- File cache: node-local `/tmp/$USER/cutlass_python_cache` (override `CUTE_DSL_CACHE_DIR`), used by the
  implicit path only. Use a fresh `CUTE_DSL_CACHE_DIR` per A/B arm when the implicit path is involved.
- Libraries that wrap `cute.compile` inherit this. The cuDNN frontend's DSA backward
  (`flash_attn_bwd_sm90`, cuDNN frontend 1.30) keeps executors in in-process dicts (`.compile_cache`,
  `.compile_cache_pre`, `.compile_cache_post`), so their sizes count its compiles exactly. A second process
  on the same filled caches recompiled all 6 kernels (about 2.5 s per main-kernel key on H200), so
  "warm" runs of such a backend are not warmer.
- Cross-process cache for a TVM-FFI executor (verified 2026-10-11, H200, DSL 4.7.1):
  `compiled.export_to_c("k.o", function_name="k")` once, then in later processes
  `getattr(cute.runtime.load_module("k.o", enable_tvm_ffi=True), "k")`. It loads the `.o` with JITLink (no gcc),
  in 3-11 ms against 1.3-3.3 s of compile, gives bitwise-identical outputs, and costs no extra host time per call.
  This TVM-FFI load path skips the DSL's version check, so key the file on the DSL version, the arch and the
  kernel sources yourself. Prototype: `~/tmp/dsv4-sparse-attn-bench/compile-avoidance/proto/cute_aot_cache.py`.
- A Python constant used only as a bound still shapes codegen: the cuDNN DSA backward's `max_topk` clamp at
  640 or 16384 gave the same SASS (4 immediates differ), but at `2**31 - 1` it added 120 instructions and about
  1% forward+backward time.

For dumps, line info, registers and spills, the Blackwell and DSL 4.8 notes, and copies into swizzled shared memory, see `../kernels/cute-dsl/authoring.md`.
