# Fusion patterns for GEMM kernels

Verified 2026-10-22 on 8x H200 (NV18 NVLink between every GPU pair) with Triton 3.8.0 and torch 2.14.1+cu130, while fusing communication and elementwise ops into a persistent Triton grouped GEMM for mixture-of-experts (MoE) expert parallelism. The rules are general; the numbers are evidence from that kernel.

Notation: the GEMM computes `out[m, n] = A[m, k] B[k, n]` in output tiles of `BLOCK_M x BLOCK_N`. Each `BLOCK_M` slice of A is read by `N / BLOCK_N` output tiles (the "N tiles"), so anything fused into the A loads runs once per N tile, while anything fused into the epilogue runs once per output element. Count how many times each fused load or computation repeats before writing the kernel. Symmetric memory means buffers allocated identically on every rank, so a kernel can load from or store to a peer GPU's copy directly over NVLink (a peer load or store).

## Peer gathers: do not fuse into a re-read operand

- Observed on H200: peer loads got no reuse from the local L2. A gather fused into the GEMM's A loads refetched each A slice over NVLink once per N tile.
- Evidence, 2 ranks with every A slice read from the peer (402 MB of A per rank), fused peer gather vs the same GEMM on a local operand vs a separate gather kernel then the GEMM:

| GEMM | N tiles | Fused gather | Local operand | Gather, then GEMM |
|---|---|---|---|---|
| Forward, fused gate and up projection | 16 | 19.4 ms | 2.47 ms | 3.45 ms |
| Input gradient, down projection | 8 | 9.7 ms | 1.25 ms | 2.37 ms |

- The fused times imply N tiles x 402 MB of NVLink traffic at about 333 GB/s, the plain peer-copy rate.
- Rule: use a separate gather kernel unless the fused kernel guarantees each A slice is fetched over NVLink once, for example one CTA (thread block) keeping its whole operand panel resident for all N tiles. Here one `BLOCK_M x K` panel is 128 x 4096 BF16 = 1 MB, far over the 227 KB of shared memory per CTA. Tile order alone (grouping an M slice's N tiles in time) was not tested and is not a guarantee, since the local L2 did not serve the repeats.
- Before building the fused kernel, time a prototype of the fused load pattern against a separate copy.

## Peer scatters: fuse into the epilogue

- Storing each output token (one index along M) straight to its destination on a peer works well, because the epilogue writes each element exactly once.
- Pass an int64 table with one absolute destination address per index along M, 0 meaning skip. Build the per-token pointers with `tl.multiple_of(addr.to(tl.pointer_type(tl.bfloat16)), 16)` (the hint counts bytes, whatever the element type), mask tokens whose address is 0, and check the PTX for `st.global.v4`.
- Removing the local staging write and the separate scatter kernel cut end-to-end MoE forward time 12 to 15% and forward plus backward 7.5 to 14% on 8 ranks, with outputs bitwise equal to the unfused path.
- No fence inside the kernel was needed: the kernel boundary orders the stores, and the system-scope release/acquire barrier across ranks that already ran after the scatter makes them visible to the peers.

## Two halves of the output along N (SwiGLU)

SwiGLU computes `silu(gate) * up`, where the GEMM's output features `[0, F)` are `gate` and `[F, 2F)` are `up`. A plain tile holds `BLOCK_N` consecutive features, so the matching `up` features sit in a different tile.

- Interleave the halves at load time instead of changing the MMA: view the weight `[E, 2F, K]` as `[E, 2, F, K]` and build one TMA (tensor memory accelerator, see `triton/hopper.md`) block descriptor with block `[1, 2, BLOCK_N // 2, BLOCK_K]`. `tl.reshape` the loaded tile to `(BLOCK_N, BLOCK_K)`: one MMA tile then holds `BLOCK_N / 2` gate features and the matching `up` features.
- Split the accumulator with `tl.reshape(acc, (BLOCK_M, 2, BLOCK_N // 2))`, `tl.permute(..., (0, 2, 1))`, then `tl.split`, which yields `gate` and `up`, each `(BLOCK_M, BLOCK_N // 2)`.
- MMA width, operands and reduction order are unchanged, and the epilogue rounds `gate` and `up` to BF16 before SwiGLU exactly as the unfused path stores and reloads them, so outputs were bitwise equal to the unfused GEMM followed by an elementwise kernel.

## Heavy epilogue math spills

- A sigmoid epilogue in FP32 (libdevice `exp` and an IEEE reciprocal) on a 128 x 256 tile at 8 warps hit 255 registers and 30 spills. Processing the tile in two halves along N (`tl.reshape`, `tl.permute`, `tl.split`, and a small `@triton.jit` helper called once per half) gave 254 registers and 0 spills, with identical outputs. The read-modify-write case is in `triton/hopper.md` ("Silent slowdowns").
- Check `ck.n_spills` after adding any epilogue math (`triton/hopper.md`, "Inspect the compiled kernel").

## Prologue fusion recomputes per N tile

- An elementwise producer fused into a GEMM's A loads (the prologue) is recomputed once per N tile. On a 49152 x 4096 operand with 16 N tiles that is about 3.2e9 sigmoid evaluations. Not measured: at roughly 25 instructions per IEEE sigmoid on 132 SMs, that is an estimated 2 to 3 ms, against a possible saving of 0.2 to 0.6 ms from skipping the separate kernel.
- Prefer fusing the producer into the epilogue of the GEMM that writes the operand, where each element is computed once. If a buffer's lifetime blocks that (the buffer the epilogue would write is still in use), reorder independent launches to free it first.
