---
name: kernels
description: Write and structure GPU kernels in Triton or CuTe DSL, with the compiled code checked at every step. Use when writing, porting, fusing or tuning a GPU kernel; deciding whether and where to fuse an op or a communication step into a GEMM (prologue, epilogue, operand loads); or reading compiled artifacts while writing it (TTGIR, PTX, SASS, register and spill counts, shared memory) to find a pipelining, register or spill regression. To measure whether a change helped, use the profiling skill.
---

# Kernels

Paths in this skill are relative to this skill's directory. Scripts live in the profiling skill (`../profiling/scripts/`); run them as their module docstrings say.

## Rule: inspect the compiled kernel after every structural change

Many kernel regressions are silent: the kernel stays correct and only gets slower. After every structural change (a new fusion, a moved pointer computation, a new epilogue op, a different tile or stage count), check the compiled artifacts before timing: pipelining and MMA counts in the IR, vector widths in PTX, `n_regs`, `n_spills` and shared memory. When the change should not alter arithmetic, check outputs bitwise (`torch.equal`) against the unfused or previous kernel. Then measure with the profiling skill (`../profiling/SKILL.md`): op timing with `bench_ops.py`, the A/B hygiene rules, ncu for why.

## Rule: compute the floor before building a kernel

Before writing a new kernel or producer design, do the arithmetic: bytes over the link or memory rate, the per-SM rate times the SMs the design can spare, and how many SMs stay co-resident for the rest of the work. Then measure the critical path alone (for example the operand loads without the MMA). If that floor already loses to the current kernel, stop: one such floor measurement ruled out a cluster-multicast GEMM in about an hour (`fusion.md`).

## Pick the doc by the question

Read only what the matching line names.

Triton on Hopper (`triton/hopper.md`):
- Is the kernel still pipelined, using WGMMA, overlapping MMAs, flattened, loading 128 bits per thread, and spill-free? "Inspect the compiled kernel".
- The kernel is correct but slower after a change (strides, `tl.where` on pointers, base pointers loaded from device memory, per-tile reductions, epilogue spills, `num_stages`)? "Silent slowdowns".
- TMA descriptors, transposed shared-memory operands, or warp specialization from Triton? "Hopper features from Triton".
- A persistent GEMM pays a pipeline refill and an exposed epilogue per output tile? "Flattening a persistent loop".
- Programs signal each other through global flags: release/acquire recipes, a spin loop that must exit uniformly across the CTA, a watchdog that traps instead of hanging? "Cross-CTA flags, claims and spin loops".

CuTe DSL (`cute-dsl/authoring.md`):
- PTX/SASS/IR dumps, line info, stable kernel names, register counts, spills and register caps, DSL 4.8 on Blackwell, copies into swizzled shared memory, TMA copy hangs, per-row bulk copies from raw (peer) addresses on sm90.
- Compile vs launch cost, executor caching and host overhead per call are measurement: `../profiling/tools/cute-dsl.md`.

Fusion (`fusion.md`):
- Should a peer gather or scatter (NVLink, symmetric memory) go inside a GEMM, and where?
- How to overlap a gather with the GEMM that consumes it in one launch (producer and consumer roles, ticket claiming, forward progress), and which producer (pull, push, copy engine, cluster multicast, a side-stream bulk-copy kernel) is fastest? Side-stream producer placement, lazy-load deadlock and host cost?
- Cross-rank counters and flags that stay correct under CUDA graph replay; symmetric-memory addresses across processes?
- Removing or adding a shape guard on a fused kernel?
- Should an elementwise op go in a GEMM's prologue or epilogue?
- How to fuse an op that needs two separated halves of the GEMM output along N (SwiGLU), without changing MMA arithmetic?
- A new epilogue op made the kernel spill?

Compiled code, any compiler:
- Did a change alter a kernel's generated code at all, and which instructions changed? `../profiling/scripts/artifact_diff.py`; `../profiling/tools/sass.md`.
- Do two kernels (TileLang, CuTe DSL, Triton, CUDA) share a design: MMA flavor, TMA vs `cp.async`, barriers, registers, spills by source line? `../profiling/tools/sass.md` (`../profiling/scripts/sass_inventory.py`).

Measuring the result: did the change help, by how much, and why is it still slow? The profiling skill (`../profiling/SKILL.md`).
