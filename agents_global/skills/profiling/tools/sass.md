# Comparing kernels at the SASS level

Whether two kernels from different compilers (TileLang, CuTe DSL, Triton, CUDA) share a design: MMA flavor,
async copies, barriers, registers and spills. Verified 2026-10-10 and 2026-10-11 on H200 (sm90a).

## Getting the cubin

- CuTe DSL: `CUTE_DSL_KEEP=cubin`, see `tools/cute-dsl.md` for dumps and line info.
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
