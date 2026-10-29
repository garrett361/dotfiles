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
- Rule: never load a re-read operand straight from peer memory. Either keep each A slice fetched over NVLink once by construction (one CTA (thread block) keeping its whole operand panel resident for all N tiles; here one `BLOCK_M x K` panel is 128 x 4096 BF16 = 1 MB, far over the 227 KB of shared memory per CTA), or gather each row once into a local buffer inside the same launch and have the GEMM read it locally (next section), which beat the separate gather kernel. Tile order alone (grouping an M slice's N tiles in time) was not tested and is not a guarantee, since the local L2 did not serve the repeats.
- Before building the fused kernel, time a prototype of the fused load pattern against a separate copy.

## Peer gathers: gather once in the same launch (role split)

The design that won: one persistent launch in which a few programs gather rows into a local buffer and publish per-tile flags, while the rest run GEMM tiles that wait on the flags and then load A locally. Systems that fuse dispatch into the expert GEMM on Hopper (ThunderKittens' MoE dispatch GEMM, Triton-distributed's fused all-to-all, PyTorch's `_async_input_mm`) share this shape: gather once, signal per chunk, read locally.

- Roles: grid `P = min(num_sms, G + max_tiles)`. Programs `pid < G` are gather programs; programs `pid >= G` run the GEMM's tiles unchanged over `P - G` programs. Keep the GEMM mainloop and epilogue identical to the unfused kernel, so outputs stay bitwise equal; the only addition is a wait before each tile's K loop.
- Units and flags: a unit is `SUB` consecutive rows of one group (e.g. one expert), with `BLOCK_M % SUB == 0`. Number units in the GEMM's tile order, so the first tiles' rows arrive first. Keep one int32 flag per (group, M tile); a tile proceeds once its flag reaches `cdiv(rows_in_tile, SUB)`. Zero the flags per launch (`torch.zeros`, a memset node under CUDA graph capture). Map a unit index to its group with a vectorized cumsum over per-group unit counts, not a loop of scalar loads.
- Ticket claiming: every producer claims its next unit with a relaxed `atomic_add` on one global ticket, until the ticket passes the unit count. Static unit assignment would tie a tile's progress to one specific program being resident.
- Self-help, for forward progress: before each tile, a GEMM program loops: if the flag is complete, proceed; else if the ticket has not passed the tile's last unit, claim the next unit and gather it exactly like a gather program; else spin, because every missing unit is held by a running program. Only running programs claim and gathering never waits, so the loop cannot deadlock, and the kernel stays correct with `G = 0` (self-help only) or if gather programs exit early (a test-only constexpr that makes them exit exercises self-help deterministically).
- Flag recipes, the CTA-uniform spin exit, and the trap watchdog in Triton: `triton/hopper.md`, "Cross-CTA flags, claims and spin loops".
- Do not split producer and consumer across two streams when the consumer grid fills the GPU. A side-stream gather kernel plus a flag-waiting GEMM on all 132 SMs deadlocked when a gather CTA (183 registers x 128 threads) could not fit beside a GEMM CTA: the GEMM CTAs spun on flags nothing could set. With the GEMM shrunk to 116 programs it worked (2.79 to 2.82 ms at 2 ranks, about the same as the single-launch role split). A side-stream producer that does work is in "Side-stream producer on the SMs the GEMM leaves" below.
- Keep the GEMM's tile order. Ordering tiles by when their rows become available mixed experts within each `GROUP_M` band and lost L2 reuse of the weights: the same GEMM took 3.349 ms in availability order vs 2.926 ms in natural order (+15%).
- Evidence, 8x H200, 32 local experts x 1536 rows (M = 49152), K = N = 4096, BF16, every A row from a random peer, median over ranks: separate gather kernel then GEMM 3.459 ms, role split with `G = 16` and `SUB = 32` 2.713 ms, GEMM on a local operand 2.201 ms, all bitwise equal. In production per-launch timing (power-capped sustained loops, 8 ranks) the role split gained 1.14x on the forward gate and up projection (3.495 to 3.072 ms at `G = 12`) and 1.34x on the down projection's input gradient (N = 2048; 2.303 to 1.719 ms at `G = 24`). The best `G` differs per GEMM, so sweep and store it per mode; `G = 0` still gained 1.03x.
- What limits it is the power cap, not the flags: in-kernel clocks (`%clock64` against `%globaltimer`) showed the overlapped kernel at 1314 to 1394 MHz vs about 1540 MHz for the GEMM alone at the 700 W cap, and scaling the GEMM-alone time by that clock ratio predicted the overlapped time within 1%. Flag waits cost 45 to 55 us per GEMM program. Under the concurrent GEMM the gather's per-SM pull rate halved (27.5 to 13 to 14 GB/s), so a 1.24 ms gather took about 2.0 ms.
- Under the power cap the fused arm cannot match the separate arm's clock, so fix the decision metric before timing (raw ms, same node and session, ABBA order; clock-normalized only as a ceiling): `../profiling/tools/do-bench.md`, "Power cap and clocks". End-to-end time also cannot say how much communication a design hides or where the rest goes; time the per-launch decomposition in `../profiling/tools/exposed-comm.md` (communication alone, GEMM alone on all SMs and on the SMs left, in-kernel waits, residual). Here it showed that the residual exposure of a 3 ms forward launch was mostly the first tile's wait (about 60 us per GEMM program), not steady-state flag waits (0.5 us).
- Registers: the gather took the forward GEMM from 184 to 232 registers (0 spills, pipelining and `pendings = 1` unchanged); details in `triton/hopper.md`.

## Choosing the gather producer: pull, push, copy engine, multicast

Do the arithmetic floor before building any producer: bytes over the link rate, the per-SM rate times the SMs you can spare, and the co-resident SMs left for the GEMM. Then measure the producer's load path alone, without the GEMM. That settled the multicast design below as a no-go in about an hour. Measured 2026-10-22 on 8x H200 (NV18), with every A row remote.

| Producer | Per-SM or per-GPU rate at 8 ranks | Outcome vs register pull |
|---|---|---|
| Register pull, 16-byte `.cg` loads | about 27 GB/s per SM (16 SMs saturated NVLink at 2 ranks) | chosen |
| TMA pull of peer rows | same per-SM cap; degrades less under a concurrent GEMM | within noise at 2 ranks |
| Push (stores into the peer's buffer) | 23 to 26 GB/s per SM (45 at 2 ranks) | 1.9% slower, needs more state |
| Copy engine (`copy_` from a peer view) | about 200 GB/s per GPU vs 316 for SM pull | 1.3x to 1.6x slower |
| Cluster multicast, 128 B per row | about 160 M deliveries per s per SM | load path alone slower than all of pull |

- Push: the 2-rank rate did not carry to 8-way fan-out. Push also needs a buffer every peer can write (symmetric), a source-side routing table, and receiver-side zero fill, and it allows no self-help, since the data comes from remote programs, so push programs must be resident on every rank.
- Copy engine: copy engines cannot gather routed rows inside a graph, so the variant replicated whole peer slabs (1.3 to 1.8x the bytes actually needed). Replication alone took 2.38 to 2.51 ms, about as long as the whole GEMM, and every early M tile had rows from every source rank, so waiting per source serialized copy then GEMM. Copy-engine arms lost (4.21 to 4.96 ms vs pull 3.17 to 3.21 ms) even though their SMs ran at 1920 to 1980 MHz.
- Cluster multicast (`cp.async.bulk ... .multicast::cluster` from peer memory, one NVLink fetch delivered to C CTAs): with `BLOCK_K = 64` each routed row is one 128 B delivery per K block. The A path alone, with no MMA and no B loads, took 2.75 ms at C = 16 and 3.31 ms at C = 8, against 2.71 ms for the whole role-split pull kernel. The limit was the delivery rate, about 2.3 TB/s in total, while a dense-speed GEMM needs about 2.9 TB/s of A delivered; NVLink ran at only 146 GB/s. Splitting the stage barrier or adding producer warps did not raise it. 256 B rows (`BLOCK_K = 128`) reached 1.39 ms at 4 stages, but only 2 stages fit beside the GEMM's tiles, and the 2-stage floor was 2.03 ms.
- Clusters cost SMs: `cudaOccupancyMaxActiveClusters` on H200 at 1 CTA per SM gives 132, 132, 120, 120 and 112 co-resident SMs for C = 1, 2, 4, 8 and 16 (C = 16 is non-portable).
- Remote stage release in a cluster pipeline: one `mbarrier.arrive.release.cluster.shared::cluster` per stage serialized the stage loop at about 1.5 to 1.9 us per stage. CUTLASS's form, `mbarrier.arrive.shared::cluster.b64` (CTA-scope release, the default), was as fast as `.relaxed.cluster` and took the C = 16 floor from 6.65 to 2.75 ms.

## Side-stream producer on the SMs the GEMM leaves

A variant of the role split: the producer is a separate kernel on a side stream, sized to the SMs the GEMM leaves free, and the GEMM keeps the role-split consumer (flag wait plus self-help, with `G = 0` gather programs and grid `num_sms - side_sms`). Measured 2026-10-22/23 on 8x H200 with a CuTe DSL 4.8 producer that copies each row with one `cp.async.bulk` global to shared and one shared to global (`cute-dsl/authoring.md`, "Bulk copies from raw addresses"); outputs bitwise equal to the separate gather path.

- Placement: the producer CTAs never shared an SM with the full-SM persistent GEMM CTAs (241 registers x 256 threads and 147 KB of shared memory per GEMM CTA), so they run only on the `num_sms - P` free SMs. With more single-warp producer CTAs than free SMs, the order in which the two streams dispatch decided placement: producer CTAs landed on would-be GEMM SMs and whole timing windows went from about 2.9 to 3.6 ms. Launch exactly one CTA per free SM with 2 to 4 independent producer warps (each with its own stages, mbarriers and ticket claims); the result then no longer depends on launch order. With no free SMs and no self-help it deadlocks (the two-stream bullet above); with self-help it stays correct but nothing overlaps.
- Lazy module loading can deadlock: when the producer kernel's first-ever launch happened while the flag-waiting GEMM was already spinning, the host blocked inside the launch and the node hung (reproduced twice; `CUDA_MODULE_LOADING=EAGER` did not help). Launch the producer once with zero work before any concurrent use or graph capture, and raise if the first launch would happen under capture.
- Producer throughput: per warp it was bound by the wait for the shared-to-global read and by draining at each unit end. Lagging `cp.async.bulk.wait_group.read` by a few groups (committing empty groups for skipped rows, so the count stays uniform) took 16 producer warps from 1.73 to 1.38 ms. Alone, 16 CTAs x 2 warps gathered at 318 GB/s (1.265 ms), NVLink-bound and equal to a 528-CTA Triton register gather. Draining with `wait_group 0` per unit before publishing cost about 4% of throughput (estimated).
- Where it wins: SM share. Per launch against in-kernel gather programs, on a large shape (K = 4096, about 3 ms per launch) and a small one (K = 2048, about 0.6 ms), it gained 1.00x to 1.08x (large forward 3.085 vs 3.081 ms, large input gradient 1.719 vs 1.673 ms, small forward 0.631 vs 0.587 ms). On the input gradient, 12 side SMs replaced 24 gather programs and the SM-share cost fell from 0.12 to 0.05 ms per launch, while the first tile's wait grew from about 60 to about 105 us, because GEMM programs self-helped about 120 units per launch. The best side-SM count differed by shape (8 to 12 on the large shape, 16 to 24 on the small one), so store it per mode.
- Host cost: the side stream adds host work per call (fork and join events, one more launch, `record_stream` in eager mode). On a short step (3.3 ms of GPU work per 8-rank forward plus backward) the side-stream design ran 7.9% slower end to end than in-kernel gather programs although its fused GEMMs were faster (1.99 vs 2.05 ms): one rank's host fell about 1.3 ms per step behind, and the other 7 ranks absorbed it as 0.53 ms more exposed time in the per-step barrier. On 15 to 21 ms steps the two designs tied (+0.1% and +0.3%). Before preferring a side-stream producer for short steps, check per-rank host slack (`../profiling/tools/exposed-comm.md`, "Step level").

## Cross-rank flags and counters under CUDA graphs

- Symmetric-memory peer virtual addresses differ per process: rank A's mapping of rank B's buffer is not at the address rank B or rank C uses. A source rank cannot turn a receiver's absolute-address table into offsets with its own `buffer_ptrs`; publish each rank's `buffer_ptrs` in symmetric memory, or keep tables in (rank, row) form.
- Counters that are never reset survive graph replay if every slot gets a constant number of credits per epoch: the sources add the rows they wrote, and the receiver adds credits for the rest (rows it zero-fills, unused slots), so the wait is `counter - epoch * CREDITS >= 0` even when the routing changes between replays. Keep the epoch in device memory, since a host-side epoch argument is frozen into the graph. When releasing per-segment counts per unit, count the unit's last lane as a segment end. Verified by replaying one captured graph across 5 routing configurations, forward then reverse, with eager runs interleaved.
- SM-free flag writes from a stream are graph-capturable: `torch.ops.symm_mem.stream_write_value32_` (it needs a flat `uint32` tensor, so pass `int32_tensor.view(torch.uint32)`) and cuda-python `cuStreamWriteValue32` both replayed correctly.

## Shape guards on fused kernels

- Before deleting a shape guard on a fused kernel, check every dimension it could protect (tile masks, TMA stride alignment, pointer fallbacks), then add a bitwise test against the unfused path at the formerly rejected shape, rather than only deleting the rejection test.
- Before adding a guard for a claimed aliasing hazard in an allocator that packs aligned buffers, read the dimension validation and the planned offsets: validation often forces sizes to multiples of the alignment, which makes the unaligned case unreachable. Verify any hazard claim from a plan with an independent reproduction before coding the guard: a claimed overlap between two planned buffers turned out unreachable through the public configuration (hidden size must be a multiple of 64, so the BF16 buffer sizes are already 128-byte aligned); a mirror of the planner overlapped only for rejected sizes, and 10 real configurations, 7 of them with the claimed unaligned size, planned 0 overlapping bytes and changed 0 bytes of the protected buffer.

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
