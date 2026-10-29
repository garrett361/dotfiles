# Exposed communication: how much of a communication step an implementation hides

Status: the decomposition is validated by known-answer controls (`scripts/exposed_comm_controls.py`, section "Validation") on H200 (sm90), Triton 3.8, torch 2.14, local and 2-GPU peer copies, only when every arm runs at the same SM clock. Under the power cap the controls refute the clock normalization. The event recorder moves the controls' kernels by -0.5 to +0.8% (local and peer), after the probe and spin-wait redesign in "Recording waits inside a Triton kernel". First applied to a dispatch gather fused into a persistent grouped GEMM (8x H200, 2026-10-22), which ran at mismatched clocks, so those numbers mix clock credit with exposed communication.

End-to-end time alone cannot separate "hid more communication" from "gave up compute elsewhere": a fused kernel can be faster than separate launches while still exposing most of its communication, or slower while hiding all of it behind SMs it took from the GEMM. This method times a few extra arms per launch and records when the GEMM programs wait, so every implementation's time over the dense GEMM splits into the same named parts.

## Arms to time per launch

Time every arm in the production calling convention (`tools/do-bench.md`, record and replay), in one ABBA process with one clock log per arm (`bench_ops.py --distributed`, `gpu_clocks.py`):

| symbol | arm |
|---|---|
| C | the communication alone (the separate copy kernel; for a side-stream producer, the producer alone on its SMs) |
| G_full | the GEMM alone on already-communicated data, all SMs: the dense roofline |
| G_P | the implementation's own GEMM binary with no communication, its flags preset ready, at the program cap it leaves the GEMM (SMs minus gather programs or side SMs) |
| T | the implementation: separate launches, fused kernel, or side-stream producer plus GEMM |
| T_rec | the implementation with the event recorder on (overhead check, and the source of the events) |

`scripts/exposed_comm.py` reads the `bench_ops.py --csv` output, the per-arm clock logs and the recorder's event tables, and prints the decomposition (definitions in its docstring):

```
E = T - G_full = (a) SM share [G_P - G_full] + (b) direct wait [from events] + (c) residual
H = 1 - E / C,   H_P = 1 - (T - G_P) / C,   H_ref = 1 - E / E_separate
```

(b) is the delay from the launch's first program start to the start of the GEMM program that ends last, plus that program's summed tile waits (start of the tile to passing its data-ready flag, self-help copies included), on the slowest rank. For separate launches, record both kernels into one event table per launch (the copy kernel's programs with a non-GEMM role) and pass `events=` together with `direct`: the start delay then measures the copy kernel and launch gap. Without events a `direct` arm's (b) is assumed to be C and printed as `assumed C`. Every tile pays a flag poll even when its data is ready (about 0.4 us per tile in the controls and in the production fused gather), which appears in (b). With static round-robin tile assignment every program does about the same compute, so the kernel end moves by the last program's waits; the mean over programs is printed beside it as a check. (c) holds what neither explains: memory, L2 and NoC contention between the copy and the GEMM, and clock differences. A negative (c) means (b) overcounts (a waiting program frees bandwidth for the others).

## Recording waits inside a Triton kernel

Copy `scripts/triton_event_recorder.py` next to the kernel (it is meant to be copied, like `cuda_timer.py`). It provides `globaltimer()`, `smid()`, `rec_put()` and `rec_close()` for `@triton.jit` code and an `EventRecorder` that owns the buffer and writes the tidy table of `intra_kernel_events.py`, so `intra_kernel_intervals.py` and `intra_kernel_ab_figure.py` read it unchanged.

- Instrument a copy of the tree with a script that applies exact-match patches (each anchor must match once), so the instrumentation is reviewable, reapplicable to a later tree, and fails loudly when the kernel source moved.
- Gate every probe behind `RECORD: tl.constexpr = False` and enable it from the host only for the recorded arm, so the unrecorded build is the original kernel.
- Events per GEMM tile: tile start, flag wait passed (`tile_ready`), tile end; per self-help unit inside the wait: a `help` range; per producer unit: claim to publish. Read the timer after the spin loop that consumes the flag, so the read is ordered after the wait.
- Rotate the recorder over the last few launches (4 here) of the timed loop: the recorded launches are then warm and the arm's own timing is the overhead measurement.

Recorder overhead is a compiler effect, not the cost of the stores. Measured in the controls' persistent GEMM (cp.async plus WGMMA K loop, 27 tiles per program, 3 probes per tile, H200, idle-padded at 1980 MHz):
- Probes written in Triton (an `if slot < cap` with three scalar `tl.store`s per event, or only timer reads summed into a Triton value, or the stores without timer reads, or per-thread register buffers flushed at program end) all made the plain GEMM 3.7 to 4.9% slower, although its K loop stayed at 85 to 91 instructions (85 unrecorded). Dropping the tile_end probe did not help (+6.9%).
- One volatile asm block per event, where thread 0 reads `%globaltimer` and makes one 16-byte store and nothing flows back into Triton values (the current `rec_put`), cost +0.5%. A second 16-byte store in the same block (to keep event and payload in separate words) cost +2.4% instead of +0.7% in the no-comm and overlap arms, so the event id and an int32 payload share one word.
- Moving the program start and end probes into asm too (no `t_start` held in a register) flipped ptxas's allocation of the K loop: 103 instead of 87 instructions, 8 `R2UR` register-to-uniform moves inside the loop, and +3 to +11%.
- The waiting kernels showed the same flip in the other direction. With a Triton spin (`while tl.min(acquire_load(flag + lanes)) < target`), the unrecorded build's K loop had 109 instructions with 6 uniform-datapath ones (16 `R2UR`) against 85 with 31 in the plain GEMM, and each of six probe designs restored an 83 to 89 instruction loop. So the recorded build ran 2 to 5% faster than the unrecorded one. A spin in one asm block (each thread loops on its own acquire load) compiles the waiting kernel's K loop like the plain GEMM's in both builds.

Design rule: write each probe as one asm block that stores from one thread and returns nothing used, keep the spin wait out of Triton control flow, and compare the hot loop of the recorded and unrecorded builds (SASS instruction count and uniform `U*` instructions of the innermost MMA loop; `exposed_comm_controls.py` prints them) before trusting a ratio. A changed hot loop means the two builds are different kernels. Then measure the recorded vs unrecorded ratio of every kernel (`recorded=LABEL` in an `--arm` prints it and flags it above 1%). When it is over 1%, (b) comes from a differently compiled kernel than T and (c) absorbs the difference, up to about `|ratio - 1| * T`. With the earlier Triton-level probes, the dispatch gather's fused kernel measured -0.9 to +0.5% (flash FPROP 3.097 vs 3.091 ms), the unrecorded build of the instrumented copy timed 1.00x the original, and its normalized PTX was identical (20 of 20 specializations), so the gate costs nothing. The traced span (first program start to last program end, slowest rank) was within -1.5 to +2.2% of the CUDA-event time.

## Validation

`scripts/exposed_comm_controls.py` runs synthetic arms with known answers through the same `exposed_comm.analyze`, `parse_arm`, `event_summary` and clock-log code users run, and exits nonzero if a check fails. Its kernel is a persistent tiled BF16 GEMM whose first programs can copy `a` operand rows from `src` and publish per-M-tile flags (CTA barrier plus gpu-scope release add; GEMM tiles spin on a gpu-scope acquire with a CTA-uniform exit). Tolerances are 4 times the root sum of squares of each involved label's spread over 3 ABBA rounds, plus 10 us for launch gaps, plus 10 us and 1 us per tile for event-based (b).

| arm | known answer checked |
|---|---|
| serial (copy kernel, then GEMM kernel) | E = C, measured (b) = C, (c) = 0 |
| wait-all (fused, every tile waits for all units) | T - G_P = C, measured (b) = C |
| no-comm (fused, flags preset, no copy) | (b) = flag polls only; T - plain G_P reported |
| overlap (fused, only units needed in the last eighth copied) | (b) = flag polls only, T = G_P, H_P = H_max |
| recorder | span within 3% of CUDA-event time, recorded within 1% of unrecorded, no timer in unrecorded PTX |
| negative controls (must fail) | wait-all mutant that skips the wait: output and (b) = C; overlap analyzed as `direct`: (b) = 0 |
| capped (`--capped`, serial only, at the power cap) | clock-normalized H = 0, given raw H is not already 0 |

Measured 2026-10-24 on one H200 (local) and two H200 (peer over NVLink), all arms at 1980 MHz with no power-cap samples (SM clocks could not be locked: no admin rights):
- Every timing and event check passed, local and peer (rerun with the asm spin and probes): serial E vs C 0.468 vs 0.473 ms (peer 1.044 vs 1.037), measured (b) 0.466 (peer 1.021), wait-all T - G_P 0.468 (1.040) and (b) 0.476 (1.029), no-comm and overlap (b) 10 to 11 us of flag polls; both negative controls failed as expected. The separate arm's old assumption (b) = C held within 1.6% here, but in the capped run measured (b) exceeded C by 5% (0.932 vs 0.885 ms).
- Recorder, before the redesign: recorded vs unrecorded time off by more than 1% in 3 of 4 arms in each mode (-3.8 to +1.9%, round spreads 1 to 4 us). After it (asm probe and asm spin, 2 local and 2 peer runs, all 35 checks passed): serial -0.5 to +0.1%, wait-all -0.4 to +0.2%, no-comm +0.7%, overlap +0.5 to +0.8%. At the default sizes the K loop has 85 instructions unrecorded and 87 recorded in every build.
- Capped: raw H +25%, clock-normalized H -28%, tolerance 11%: the normalization fails, so decompose only at matched clocks.

Rerun on one node: `uv run --script scripts/exposed_comm_controls.py` (local, 1 GPU), add `--peer` (2 GPUs) or `--capped`; `--out-dir` keeps events, clock logs and `results.json`. Each run takes about 5 to 10 minutes, mostly compiling and the 1 s warmup per label and round. Exit codes: 0 all checks pass, 1 a check failed or a negative control passed, 3 invalid (arm clocks differ by over 30 MHz or hit the power cap in over 5% of samples; with `--capped`, raw H already within tolerance of 0).

## Pitfalls

- Exposed communication buys clock under a power cap. A low-power copy kernel lowers the average power, so the GEMM after it runs faster than the same GEMM back to back. In the capped control, a strictly serial copy-then-GEMM read H = +25% (GEMM at 1725 MHz in sequence vs 1380 MHz alone, (c) = -0.27 ms on a 2.1 ms GEMM); the same effect gave the dispatch gather's separate path H = 8 to 35%. Rescaling the GEMM part by `f_T / f_ref` does not fix it: in the control it overcorrected to H = -28%, because the capped GEMM ran 13% faster at a 25% higher clock, not 1 / f. Only matched clocks give a valid decomposition: lock clocks below the cap (`nvidia-smi -lgc`, needs admin rights) or keep every arm below the cap by idling between launches (the controls' default, `torch.cuda._sleep` for as long as each launch), and confirm with one clock log per arm. `exposed_comm.py` warns when a label's clock differs from G_full's by more than 30 MHz. A fused kernel's wall-time gain at the cap is still a real end-to-end result, but split it into parts only at matched clocks.
- Clocks also move with the program cap: the GEMM at fewer programs ran 75 to 150 MHz faster than at all SMs under the cap, which is another reason to decompose only at matched clocks.
- Time G_P with the implementation's own binary (wait code compiled in, flags preset, producers idle), not with the plain GEMM. In the controls, compiling the per-tile wait in cost 31 to 41 us on a 0.66 ms GEMM (5 to 6%, registers 104 to 122) with no communication at all when the spin was Triton code, and 3 to 31 us (8 runs) with the asm spin, which a plain-GEMM G_P books as (b) and (c).
- The waits depend on the rank: with uneven routing the busiest rank waits longest (small FPROP: 0.12 to 0.23 ms across ranks). Use the rank with the longest traced span, which matches the "max over ranks" timing.
- Where the wait sits matters for the fix: in the flash case nearly all of (b) was the first tile's wait (61 us median, every program), with steady-state tile waits of 0.5 us, and a self-help unit inside that first wait took 59 us against 15 us for a dedicated producer's unit; in the small case about half of (b) was self-help copying and about half of all units were copied by GEMM programs.

Multi-rank runs (measured on 8x H200 with a real fused gather, 2026-10-24):

- Match clocks by padding, not by normalizing: an idle `torch.cuda._sleep` about as long as the call, before each call and outside the timed events, kept every arm at 1980 MHz with no power-cap samples (15 of 16 runs valid). Without it the separate copy-then-GEMM arm read E - C = -0.38 ms on a 3.5 ms launch.
- A sleep-then-GEMM arm is a cheap causal test of clock credit: it lowers power with no memory or link traffic. At the cap it reproduced the separate arm's apparent hiding (-0.29 ms; the GEMM after the sleep ran at 1890 MHz against 1470 MHz back to back), and at matched clocks it read -0.01 ms.
- Keep ranks in lockstep: add one small all_reduce per call outside the timed events. Without it the ranks drift apart, a serial copy on one rank overlaps other ranks' GEMMs (the copy took 1.02 ms in sequence against 1.12 ms alone, so measured (b) fell 0.12 ms below C), and the last recorded launches of communication-heavy arms ran 0.10 to 0.15 ms slower than the timed median. With lockstep the traced spans matched the CUDA-event times within 1% and the separate arm's (b) equalled C.
- Time G_P with the implementation's own binary and its ready flags preset on the host (same cubin as the real launch); a plain GEMM at the same program cap was 0.035 to 0.052 ms faster, the compiled-in wait's cost.
- Make one untimed call per label before measuring the per-call time: a first call that compiles or starts a clock logger inflates the estimate and silently cuts the repetition count.
- C from the standalone copy kernel may not be the in-kernel copy's time. A wait-all control (every tile waits for all units) read 0.055 to 0.076 ms below C on the flash shape; a compute-skipping constexpr build of the same launch (flag wait and self-help unchanged, K loop and epilogue skipped) measured the in-kernel copy at 0.955 to 0.966 x C, and against that known answer wait-all passed in all 4 cases. The standalone copy differed from the in-kernel copy by -4.5% to +17.5% across cases, and a side-SM producer timed alone took 1.37 x C on a small shape, so check C_inkernel / C before calling a control failure a tool error, and compare implementations by H against the one standalone C.

## Step level

Per-launch decomposition says nothing about launches it does not cover. Trace one fwd+bwd step per arm (`bench_ops.py --distributed --trace`, `tools/torch-profiler.md`) and run `step_accounting.py` with `--comm` matching every communication-only kernel (copy kernels, barriers, unfused scatter, side-stream producers) and `--comm-label` naming each: a communication kernel that runs while any compute kernel runs is counted as compute, so side-stream overlap is credited automatically. Add the fused kernels' exposed part from the per-launch table (E per launch times the launches per step, an estimate) to get the step's exposed communication per arm.

- Trace each arm first in its own process. With several labels in one `bench_ops.py --trace` process, the labels traced after the first ran 12 to 25% slower in their traces (and up to 14% slower in their timing on a 3.4 ms step); reversing the arm order moved the slowdown with the position, not the arm.
- Check the reconciliation: per-launch E predicted the step gain. In the flash case the separate path exposed 2.28 ms per step of copy kernels plus 0.47 ms of barriers; the fused path exposed 0.60 ms of barriers plus about 0.71 ms inside the fused kernels. The per-launch E difference (0.98 ms) minus the barrier increase (0.14 ms) gave 0.84 ms against 0.85 ms measured untraced. Using the copy kernels' traced duration instead of the separate arm's E would have overstated the gain by the clock credit above.
- Read the barrier rows per rank (`step_accounting.py --per-rank`). With a symmetric-memory barrier every step, one rank whose host launches late shows up on every other rank as exposed barrier time, and the mean over ranks books it as communication. Measured 2026-10-23 on 8x H200: a side-stream producer design ran a 3.5 ms forward plus backward step 7.9% slower than in-kernel gather programs although its fused GEMMs were faster (1.99 vs 2.05 ms); per rank, one rank sat idle "host late" for about 1.3 ms per step (mostly before one launch in the backward), and the other 7 ranks showed 0.53 ms more barrier. That points at per-call host work (launches, events, `record_stream`), not at the communication.
