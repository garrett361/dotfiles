# Triton kernel performance on Hopper

Verified 2026-10-21/22 on H200 (sm90a) with Triton 3.8.0 and torch 2.14.1+cu130, on persistent grouped GEMM kernels (BF16 inputs, FP32 accumulation, WGMMA, the Hopper warpgroup MMA). Many of these regressions are silent: the kernel stays correct and only gets slower, so inspect the compiled kernel after every structural change, before timing it.

## Inspect the compiled kernel

- After one launch, `fn.device_caches[device][0]` (with `fn` the `@triton.jit` function and `device` the CUDA device index) maps each specialization key to a compiled kernel `ck`: `ck.asm["ttgir"]` (Triton GPU IR), `ck.asm["ptx"]`, `ck.n_regs`, `ck.n_spills`, `ck.metadata.shared` (bytes of shared memory), `ck.metadata.num_warps`. Loop over `fn.device_caches.values()` and `dc[0].items()` to dump every specialization, from a script in the investigation's `inputs/` (see the profiling skill).
- Counts worth printing for every variant:

| Check | Where | Healthy |
|---|---|---|
| cp.async pipelining | `async_copy_global_to_local` count in TTGIR | nonzero |
| WGMMA | `warp_group_dot ` count in TTGIR | one per MMA in the loop |
| MMA overlap | `pendings = ` on `ttng.warp_group_dot_wait` in TTGIR | 1 inside the loop (0 only in the drain after it) |
| Loops after flattening | `scf.for ` count in TTGIR | one fewer per fused loop |
| 128-bit register loads | `ld.global.v4.b32` or `ld.global.cg.v4.b32` in PTX | present on the vectorized loads |
| Spills | `ck.n_spills` | 0 |

- For the mainloop's instructions, use `../profiling/tools/sass.md` (`../profiling/scripts/sass_inventory.py <TRITON_CACHE_DIR> --kernel <name>`); to see what a change altered, `../profiling/scripts/artifact_diff.py` on two fresh `TRITON_CACHE_DIR`s.
- When one kernel lags a sibling that shares its structure (e.g. the input-gradient GEMM vs the forward GEMM), profile both with `../profiling/tools/nsight-compute.md` and compare `smsp__inst_executed.sum`, registers, and the `dispatch` and `wait` stall reasons. Extra instructions with dispatch and wait stalls point at address arithmetic in the mainloop (the stride items below), not at memory.

## Silent slowdowns

- `tl.where` on the contiguous-axis pointer drops cp.async pipelining: clamping column indices with `tl.where` made the loads synchronous (120 vs 500 TFLOP/s). Clamp only the strided axis, and mask the contiguous one.
- Triton specializes integer arguments only for `== 1` and `% 16 == 0`. A runtime non-unit stride along the reduction axis of a pipelined `tl.load` made every per-thread pointer advance with a 64-bit `IMAD.WIDE` each K step: 43 more registers, 20% more instructions, 15% slower than the same kernel with a unit stride. Make such per-thread strides `tl.constexpr` (derive them from constexpr shapes when the operand is contiguous).
- The opposite holds for an increment shared by all threads: a large constexpr per-step pointer increment (`BLOCK_M * row_stride`) is materialized per pointer (`IMAD.WIDE` plus `IMAD.MOV`, 19 more instructions per step, 18 more registers, 2 to 7% slower), while a runtime stride lives in one uniform register. Use constexpr only where the runtime value multiplies per-thread offsets, and check the mainloop instruction count either way.
- A base pointer loaded from device memory (for example `buffer + tl.load(offset_ptr)`) rather than passed as a kernel argument lives in a per-thread register, and ptxas then rematerializes a carried 64-bit pointer tensor inside the mainloop (`IMAD.WIDE.U32` between HGMMA issues): dispatch stalls rose 6x, the tensor pipe fell from 92% to 84% active, and the GEMM lost 5 to 9% with identical TTGIR. Build each step's pointers as a scalar per-tile int64 base plus loop-invariant int32 offsets (`base + k0 + offs`) instead of advancing a carried pointer tensor. To isolate such a calling-convention regression, move one operand at a time to the production convention, and also call the plain-tensor path on views of the production buffer, which separates code generation from memory placement.
- `tl.multiple_of` on a pointer counts bytes: hint 16 for 128-bit loads, whatever the element type, from addresses read out of an int64 pointer table, then check PTX for `v4` loads.
- Per-tile reductions in a persistent loop (`tl.sum` or `tl.max` over a register vector of group sizes, to find a tile's group) spilled, and cost 7 to 9% at small shapes. Advance the group monotonically with scalar loads instead, e.g. a `tl.static_range` of `if group < g:` steps.
- A large FP32 epilogue spills: a read-modify-write epilogue on a 128x256 FP32 accumulator spilled 60 registers. Splitting the tile with `tl.reshape`, `tl.permute` and `tl.split` and storing the halves separately removed the spills (3.03 to 2.55 ms). The same split fixes heavy elementwise epilogues: `fusion.md`.
- `num_stages` and tile shape interact with shared memory and registers: 3 vs 4 stages moved one GEMM 20 to 27%, and one 64x256x256 configuration ran 4.7x slower. In a config sweep, print the cp.async count and spills per config, not just time.

## Hopper features from Triton

- A transposed shared-memory operand is free: WGMMA reads either operand transposed from shared memory (`.tnspA` / `.tnspB` on `HGMMA` in SASS), with no `ldmatrix.trans` or layout conversion. Don't pre-transpose weights for it.
- Host-built TMA descriptors (TMA is Hopper's bulk tensor copy engine): `triton.tools.tensor_descriptor.TensorDescriptor(t, list(t.shape), list(t.stride()), block_shape)` passed as a kernel argument. A 3-D `[E, N, K]` descriptor with block `[1, BK, BN]`, loaded with `desc.load([e, k0, n0])` and `tl.reshape`d to 2-D, works inside a `tl.range(..., num_stages=...)` pipelined loop next to cp.async loads of the other operand. It needs no allocator and is CUDA-graph capturable, but needs a 16-byte-aligned base and outer strides: keep a pointer fallback. It gained 3% on one GEMM.
- Device-built descriptors (`tl.make_tensor_descriptor` in the kernel) need `triton.set_allocator(fn)` for their scratch. That allocator is process-global, and is called on the host at every launch, including during CUDA graph capture, where the scratch comes from the graph's private pool and is freed after the launch: capture and replay worked, but only on a single stream. A per-tile descriptor whose shape ends at a group's last row bounds ragged groups with zero fill and no masks; it cut registers but gained nothing.
- `tl.range(..., warp_specialize=True)` on Hopper in Triton 3.8 is not usable: ignored at `num_warps=8` (no `ttg.warp_specialize` op in TTGIR, identical PTX), and at `num_warps=4` the warp specialization pass crashed on persistent kernels. Where it did compile (a minimal TMA GEMM) it was slower than the non-specialized kernel. Check for the `ttg.warp_specialize` op and `setmaxnreg` in PTX before believing it took effect.

## Cross-CTA flags, claims and spin loops

Verified 2026-10-22 on H200 with Triton 3.8.0, in a persistent grouped GEMM whose GEMM programs wait on per-tile flags published by gather programs in the same launch (`fusion.md`, "Peer gathers: gather once in the same launch"). Every ordering claim below was checked in PTX.

- Publish with a CTA barrier then one release atomic: `tl.debug_barrier()` followed by `tl.atomic_add(flag_ptr, 1, sem="release", scope="gpu")` on a scalar pointer, result unused, lowers to `bar.sync` then one predicated `atom.global.gpu.release.add`, with no stores in between and no result broadcast. The barrier orders every thread's stores before thread 0's release, so the release publishes the whole CTA's writes.
- Acquire with inline asm, in every thread: Triton has no acquire load, so use `tl.inline_asm_elementwise("ld.global.acquire.gpu.b32 $0, [$1];", "=r,l", [ptrs], dtype=tl.int32, is_pure=False, pack=1)` (a relaxed peek is the same with `ld.global.relaxed.gpu.b32`). Each thread that later reads the published data must acquire itself; check that `ld.global.acquire.gpu` in the PTX is unpredicated (one per thread).
- Make the spin exit CTA-uniform: Triton loads a scalar in every thread, so two threads can read different values of a flag that changes under them. If the loop body holds a barrier (`tl.debug_barrier`, or a scalar atomic whose returned value Triton broadcasts through shared memory with `bar.sync`), a thread-divergent exit splits the barriers and hangs. Load the flag as a `[NUM_THREADS]` vector of one address (`flag_ptr + tl.zeros((NUM_THREADS,), tl.int32)`) and branch on `tl.min(..., 0)`: every thread still acquires, and the reduction gives one decision per CTA. Apply the same to any peek (e.g. of a ticket counter) that decides whether to enter a claim.
- A scalar atomic whose result is used (e.g. `unit = tl.atomic_add(ticket_ptr, 1, sem="relaxed", scope="gpu")`) runs on one thread and broadcasts the result through shared memory, so the whole CTA gets one claim.
- Order the consumer's loads after the spin: the pipeline prologue's `cp.async` copies of the waited-on operand must come after the spin loop in PTX. Plain stores and `cp.async` are both generic-proxy operations, so no proxy fence is needed between a register-store producer and a `cp.async` consumer; if either side moves to TMA or `cp.async.bulk` (the async proxy), add `fence.proxy.async` between the data writes and the release.
- `tl.device_assert` is compiled out unless Triton debug mode is on, so it cannot serve as a spin watchdog. Use a predicated inline-asm trap, `tl.inline_asm_elementwise("{ .reg .pred p; setp.ne.u32 p, $1, 0; @p trap; mov.u32 $0, 0; }", "=r,r", [cond.to(tl.int32)], dtype=tl.int32, is_pure=False, pack=1)`, behind a constexpr spin limit that tests turn on and production compiles out. A mutation test (a claim that gathered the wrong unit) failed with `CUDA_ERROR_LAUNCH_FAILED` instead of hanging the node.
- A conditional barrier plus release inside a flattened, pipelined loop removes the pipelining (one TMA buffer instead of `num_stages`): nest the loops instead, with the pipelined inner loop over rows and the release after it.
- A producer role in the same kernel shares the GEMM's register allocation: gathering 32 rows per step at 8 warps took the GEMM from 184 to 232 registers with 0 spills, while the same gather as a standalone kernel at 4 warps spilled (255 registers, 116 spills). Chunk the producer's copy to about 32 values per thread per step and recheck `ck.n_spills` for every mode.

## Flattening a persistent loop

Persistent GEMMs with short reduction loops pay a pipeline refill and an unoverlapped epilogue per output tile. Flattening the tile loop and the reduction loop into one pipelined loop hides that.

- `tl.range(..., flatten=True)` silently refuses when the inner trip count varies per outer iteration (ragged groups such as experts): count `scf.for ` in TTGIR to see whether it fused.
- Manual flattening: one `tl.range` over all of a program's reduction steps, the tile prologue under `if step == 0`, the epilogue under `if step == last_step`. Reset the accumulator inside the epilogue `if` (`acc = tl.zeros(...)`), never with `tl.where(done, 0, acc)`: the `tl.where` form made the pipeliner wait on every WGMMA (`pendings = 0`, 34% slower). Carry pointers across steps and reset them at tile start (recomputing them per step cost 15%), and keep cross-warp reductions out of the loop.
- In a fused loop the epilogue's shared-memory scratch (the FP32 layout conversion) cannot reuse the live pipeline buffers. Check the sum against the 227 KB limit (232448 bytes): a 64x128x256 tile with 4 stages fit with a BF16 epilogue (229376 bytes) but not with FP32 (327680 bytes).
