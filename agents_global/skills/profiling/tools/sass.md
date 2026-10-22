# Comparing kernels at the SASS level

Whether two kernels from different compilers (TileLang, CuTe DSL, Triton, CUDA) share a design: MMA flavor,
async copies, barriers, registers and spills. Verified 2026-10-10 and 2026-10-11 on H200 (sm90a).

## Getting the cubin

- CuTe DSL: `CUTE_DSL_KEEP=cubin`, see `../kernels/cute-dsl/authoring.md` for dumps and line info.
- TileLang: the cubin lands in `$TILELANG_CACHE_DIR/<version>/cuda-binaries/*.cubin` (default
  `~/.tilelang/cache`); set a fresh `TILELANG_CACHE_DIR` per arm. In TileLang 0.1.12 the `TVMFFIKernelAdapter`
  has no `libpath`. `kernel.get_kernel_source()` on a `tilelang.jit` kernel returns the generated CUDA.
- Triton: the cubins under `$TRITON_CACHE_DIR`.
- Extensions: pass the `.so`; multi-arch binaries give one table per SASS arch.

## Reading it

- `scripts/sass_inventory.py <cache dir, cubin or .so> ...` prints, per kernel (and per SASS arch in a
  multi-arch `.so`), registers/stack/local plus static counts of `HGMMA` by shape, `HMMA`, `UTCHMMA`
  (sm100), `LDGSTS`, TMA, `LDSM`/`STSM`, barriers (`BAR.*`, mbarrier `SYNCS`) and `MUFU`. Verified on the
  TileLang DSv4 forward's cubin and its CuTe port's, on flash_mla's `.so`, and on a Triton cache, against
  `cuobjdump -sass | grep`. Pass `--kernel` on a large cache: it skips non-matching cubins before disassembly
  (3 s instead of 5.5 min on a 983-cubin Triton cache).
- MMA flavor: `HGMMA` is WGMMA (sm90a), `HMMA` is `mma.sync`. `WARPGROUP.DEPBAR.LE gsb0, 0x0` right after the
  `HGMMA`s means the WGMMA is waited on immediately (synchronous).

## Same kernel, two arms: is the code identical?

- `scripts/artifact_diff.py A_DIR B_DIR` compares every `.sass`, `.ptx` and `.ttir` under two `CUTE_DSL_DUMP_DIR`s
  or Triton caches, and tables the changed instructions with registers normalized. Verified 2026-10-21 on B300
  (sm_103a, DSL 4.8.0, Triton 3.8.0) on dist_moe dumps from two worktrees of the same code (53 artifacts, all
  identical) and from two values of a constant (one table row per changed opcode pattern).
- Raw files from two worktrees never match: Triton PTX carries `.loc` line numbers and DWARF `.section .debug_*`
  bytes that embed the source path, TTIR carries `loc(...)`, and SASS carries addresses. The script strips these.
  A Triton cache also holds several specializations under one file name, compared as a set.
- Changing an FP32 constant addend to 0.0 keeps the add: `u + 1.0` became `FADD R, RZ, R` (and `FADD2 ...,
  RZ.F32` for packed pairs), same instruction count, because `-0.0 + 0.0` is `+0.0` under IEEE and the compiler
  may not drop it. Elide such an add with a compile-time branch only if timing shows a cost.
