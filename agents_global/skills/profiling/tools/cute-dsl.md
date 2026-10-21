# CuTe DSL kernels (`cutlass.cute`): compile vs launch, dumps, registers, copies

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

## Dumps and line info

- `CUTE_DSL_KEEP=ir,ptx,cubin,sass CUTE_DSL_DUMP_DIR=<dir>` writes the clean IR, PTX, cubin and SASS per
  compiled host function (SASS via the `nvdisasm` bundled in the venv on 4.7.1; DSL 4.8 needs a separate one,
  see "Blackwell and DSL 4.8" below). Keeping `ptx`, `cubin` or `sass`
  disables the JIT cache (`dsl.py`), so implicit calls then pay a full compile each time (43-46 ms vs 18-21 ms
  with `CUTE_DSL_KEEP=ir` alone, on a trivial kernel).
- `CUTE_DSL_LINEINFO=1` maps PTX/SASS to Python `file:line` (`//## File "...py", line 37` in the SASS
  dump), and is what ncu source correlation needs (`nsight-compute.md`). The DSL docs advise validating performance with it off.
- `compiled.__ptx__` is `None` unless the compile passed `options="--keep-ptx"` (checked with and
  without `--enable-tvm-ffi`); `--keep-ptx` also writes the `.ptx` into `CUTE_DSL_DUMP_DIR`, which
  defaults to the working directory at import time, so it litters the repo when run from there.
  `compiled.__cubin__` is likewise `None` unless the compile kept it (`options="--keep-cubin"`).
- `my_kernel.set_name_prefix("name", remove_cutlass_symbol=True, keep_mangled_name=False)`, called on the
  `@cute.kernel` function inside the `@cute.jit` function before `my_kernel(...).launch(...)`, gives the GPU
  function the stable name `name_0`, convenient for `ncu -k regex:name`. The launcher that
  `my_kernel(...)` returns has no `set_name_prefix`.

## Registers and spills

- Register count: `cuobjdump --dump-resource-usage <cubin>` (`REG:`, `STACK:`, `LOCAL:`), or ncu Launch
  Statistics (the same count, but never below 16). The DSL does not print it.
- `CUTE_DSL_COMPILER_OPT='remarks{ptx}'` (or `options="remarks{ptx}"`) prints "ptxas detected register
  spills" or "ptxas detected local memory usage" with the Python source frame, and nothing for a clean
  kernel. Spill byte counts are in `cuobjdump`'s `STACK:` (8376 bytes for a forced spill).
- Register cap: `options="--ptxas-options '--maxrregcount=N --override-directive-values'"` in
  `cute.compile`. Without `--override-directive-values` the cap was silently ignored. `ptxas` flags in
  `CUTE_DSL_COMPILER_OPT` failed with an internal compiler error.
- The spill remark's source frame marks a register-pressure region, not the spilling instructions: on
  the warp-specialized DSv4 forward it pointed at a prologue line while every `LDL`/`STL` was on the
  producer's copy lines. `scripts/sass_inventory.py <cubin> --by-line LDL STL` lists the real lines
  (needs `CUTE_DSL_LINEINFO=1`).
- Warp-specialized kernels: `cute.arch.setmaxregister_decrease(n)` / `setmaxregister_increase(n)`
  appear in SASS as `USETMAXREG.DEALLOC.CTAPOOL` / `USETMAXREG.TRY_ALLOC.CTAPOOL`. `cuobjdump`'s
  `REG:` (and ncu's Registers Per Thread) stays at the launch-time count, `65536 / threads` rounded
  down to a multiple of 8 (168 at 384 threads), so judge each role's pressure by spills, not `REG:`.
- `CUTE_DSL_DUMP_DIR` must exist: with a missing directory and `CUTE_DSL_KEEP=...,sass` the compile
  died with an internal error, "Cannot dump SASS: CUBIN file does not exist".

## Blackwell and DSL 4.8

Verified 2026-10-21 on B300 SXM6 (sm_103a) with `nvidia-cutlass-dsl` 4.8.0, torch 2.14.1+cu130, SLURM jobs 2755
and 2757, against the installed DSL source (`base_dsl/env_manager.py`, `cache_helpers.py`, `dsl.py`).

- SASS dumps need `nvdisasm` at least as new as the CUDA the DSL was built with (13.4 for 4.8.0); an older one is a
  hard error at compile time ("nvdisasm ... reports version 12.9, which is not supported for SASS dumping"). The
  error suggests `pip install nvidia-cutlass-dsl[sass]`, but the 4.8.0 wheel declares no `sass` extra (only
  `cu13` and `qnx`): `uv pip install nvidia-cuda-nvdisasm` (13.4.92) works. The DSL probes that wheel first, then
  `CUDA_HOME` / `CUDA_PATH` / `nvcc` on `PATH` / `/usr/local/cuda*`; Triton's bundled `nvdisasm` is never used.
- Dumps are named `cutlass___call___<module><Class>_object_at__<argument types>`, truncated to 180 characters
  with object addresses removed (`dsl.py`). Two specializations of one kernel class with the same argument types
  get the same name, and the later compile overwrites the earlier dump: a dist_moe run with ten pipelines left 15
  `.sass` files. Dump each configuration of interest into its own `CUTE_DSL_DUMP_DIR`.
- On sm_103a the cubins are written as `<name>.sm_103a.cubin`.
- `CUTE_DSL_CACHE_DIR` is read once, at import, by `cache_helpers.get_default_generated_ir_path` (default
  `$TMPDIR/$USER/cutlass_python_cache`), even though the env-manager field of the same name is marked unread.
- To compare the artifacts of two arms (two worktrees, or two values of a compile-time constant), use
  `scripts/artifact_diff.py` on the two dump directories (`tools/sass.md`).

## Copies and swizzled shared memory (verified on the DSv4 port)

- A swizzle from `layout.inner` passed to `allocate_tensor(..., swizzle=...)` lives in the pointer type and
  is applied on dereference. Turning that pointer into a raw address (`tensor.iterator` into
  `cute.arch.cp_async_shared_global`, `.toint()`, `recast_ptr(p, None, ...)`) drops it: a 128-byte-swizzled
  tile came out with chunk `c` of row 1 at chunk `c ^ 1`. `cute.crd2idx(coord, composed_layout)` returns the
  unswizzled offset too. Copy through tensors (`cute.copy`, `autovec_copy`, indexing) instead.
- `cute.copy(CopyG2SOp atom, src, dst, pred=p)` with `p = cute.make_fragment_like(src, Boolean)` lowers a false
  predicate to `cp.async.cg.shared.global [d], [s], 16, %r` with source size 0, which zero-fills the
  destination (SASS `LDGSTS.E.BYPASS.128`). The predicate must have the source's full shape; a `(1,)`
  predicate fails IR verification.
- In a register-starved role (a 72-register producer warpgroup) that predicated `cute.copy` spilled; raw
  `cute.arch.cp_async_shared_global(dst, src, 16, "cg", cp_size=16 or 0)` with a hand-swizzled destination
  (`chunk ^ (row % 8)` for the 128-byte swizzle of 16-bit data) did not, and was 6-16% faster.
- A TMA `cute.copy` (`CopyBulkTensorTile*Op`) elects its issuing lane itself (`elect.sync` with a full
  mask in the PTX), so it must be called by all 32 lanes of a warp. Called from `if tidx == 0:` the kernel
  hung with no error. Keep only `mbarrier_arrive_and_expect_tx` behind the single-thread guard.
- To find a hang like that: `cute.printf` before and after each suspect call, then read the PTX
  (`options="--keep-ptx"` or `CUTE_DSL_KEEP=ptx`); printf output from a hung kernel appeared when
  `timeout` killed the process.
