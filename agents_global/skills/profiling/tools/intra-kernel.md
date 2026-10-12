# Intra-kernel tracing (IKET for CuTe DSL)

Status: verified on 2026-10-11 on H200 (sm90, `prime-nebius-puku-h200-gpu-*`), `nvidia-cutlass-dsl` 4.7.1,
whose wheel ships IKET and `run-iket`. Worked example: the DSv4 CuTe forward study in prime-rl branch
`exp/ds-v4-cute-intra-kernel-trace`, `benchmarks/scripts/dsv4_cute_trace/results/FINDINGS.md`.

Intra-kernel tracing records timestamps from inside a running kernel, per warp: when each warp role issued
a load, started and finished each wait, entered the epilogue. It answers "what was this warp doing, and
what was it waiting for" over a whole grid, with distributions instead of one sample.

## When to use which tool

| Question | Tool |
|---|---|
| How long does the kernel take, and did a change help? | CUDA events or torch.profiler on untraced runs |
| Which instructions do warps stall on, and why? | ncu `SourceCounters` (`tools/nsight-compute.md`) |
| Bandwidth, cache hit rates, bytes moved, pipe utilization? | ncu sections and metrics |
| When does each warp role reach and leave each wait, and which wait gates the next step? | intra-kernel tracing |
| How do CTAs interleave on an SM, and do loads across the GPU bunch up? | intra-kernel tracing |
| Launch gaps, overlap between kernels, host stalls? | Nsight Systems (IKET adds unshown entry and exit work) |

ncu sampling tells you where time goes in aggregate. Tracing tells you when, per CTA and per iteration,
which is what timing questions about latency, ordering and synchronization need. Use both, in separate runs.

## Verified recipe (H200, CuTe DSL 4.7.1)

- API (`from cutlass.cute.experimental import iket`, inside `@cute.kernel` code): `iket.mark(name, payload)`,
  `range_start` / `range_end`, `range_push` / `range_pop`, `sentinel_token(name)` for a range that crosses
  loop iterations. Payloads are Python ints (stored as 32-bit), Python floats (stored as f32) or DSL scalars.
- Calls are stripped unless IKET is enabled. `run-iket` enables it automatically for kernels JIT-compiled
  inside the profiled process. `CUTE_DSL_COMPILER_OPT=iket` or `cute.compile(..., options="iket")` builds it
  without profiling. Under `run-iket` the environment option composes with a kernel's own
  `options="--enable-tvm-ffi"`: no code change was needed.
- Run: `run-iket --output-dir DIR --clobber profile --postprocess all -- python script.py ...` (the binary is
  `.venv/bin/run-iket`). The 4.7.1 docs list `--enabled-cluster`, but the 4.7.1 CLI does not have it.
- Output: `iket_pid_<pid>.pftrace` (+ `.gz`) for ui.perfetto.dev and `iket_pid_<pid>.trace.json`. Convert the
  JSON with `scripts/intra_kernel_events.py` and analyze with `scripts/intra_kernel_intervals.py` and
  `scripts/intra_kernel_ab_figure.py` (commands under "Pipeline"). Only `profile --postprocess json` (or
  `all`) writes the JSON: the `run-iket postprocess` subcommand offers only perfetto and html.
- Timer granularity is 32 ns. Timestamps are GPU-global, so intervals between warps and SMs are valid.

## Gotchas hit

- `run-iket` runs the whole workload twice: a sizing pass, then the profiled pass. Keep the workload to a
  few launches (one cold launch plus two warm ones worked well) and analyze the warm ones
  (`intra_kernel_events.py --launches 1 2`). Any output file the script writes is written twice.
- Volume: a 16384-CTA grid with about 14 marks per warp produced 1.5 to 2.8M events per launch, a 550 to
  780 MB JSON and a 390 to 570 MB `.pftrace` for 3 launches, and took about 6 minutes, most of it
  postprocessing (single-threaded CPU). Run the postprocess and the analysis on the compute node.
- CUPTI cannot run under `run-iket` (`CUPTI_ERROR_MULTIPLE_SUBSCRIBERS_NOT_SUPPORTED`), so torch.profiler
  records no kernels there. Time traced runs with CUDA events, or take the span from the trace
  (`intra_kernel_intervals.py --spans`). Events around a call
  under `run-iket` include IKET's entry and exit work and were 16 to 28% longer than the untraced kernel time,
  while the traced warp-lifetime span was 1.3 to 6.7% longer: use the span.
- Event counts per warp must match between the two passes. With identical inputs they did (identical
  per-name counts over every launch), including marks inside data-dependent `if pair == 0:` branches.
- A `sentinel_token` range assigned inside a warp-uniform branch (`if warp == 0:`) and closed in a later
  branch worked, as did a range carried through the loop of a persistent kernel.
- No event may sit inside `cutlass.range(..., prefetch_stages=...)`. Check the kernel for that loop form.
- A mark right after an async issue (TMA, `cp.async`) measures only the issue. Mark both sides of the wait
  instead. To time when a global load's value arrives, give the mark that value as its payload: the mark
  then waits on the load's scoreboard. Put such a value-forcing mark where the code consumes the value
  anyway, or it moves the stall.
- Launch indices count the launches of every instrumented kernel in the process. When it ran more than
  one, `intra_kernel_events.py` warns and lists them; pick one with `--kernel`.
- Capturing an instrumented kernel in a CUDA graph aborted `run-iket`'s sizing pass in one try
  (`OnGraphLaunchEnd: No LaunchBufferRecord found`). Trace eager launches.
- The first launch of a process runs cold (JIT, descriptor and cache warmup): it was about 75% slower than
  later launches under `run-iket`. Keep it out of the analysis.
- In ncu, an mbarrier wait shows up as long-scoreboard stalls on `NANOSLEEP.SYNCS` in the try-wait loop,
  attributed by line info to the line after the wait.

## Marker convention

- One stable, role-prefixed name per event, shared by every variant you compare (`c_wait_q` for a
  consumer's Q wait, `p_free` for a producer's free-buffer wait ending). Stay under 30 unique names, above
  which IKET switches to a costlier encoding.
- A mark before and after every wait. A long wait means the data was late. A near-zero wait only says it had
  already arrived, so it bounds the load's latency without measuring it.
- The work item (query, tile) as payload, so persistent iterations line up with non-persistent CTAs.
- Emit each event once per iteration per warp: the analysis pairs events by occurrence number.
- Instrument a copy of the kernel per variant, so the stripped build is the original's code (check the
  SASS) and the marks appear as a reviewable diff.

## Required validation checklist

Do not explain a timing difference with a trace until every row holds. Report the results with the findings.

| check | how |
|---|---|
| stripped build = original | SASS diff shows 0 differing instructions, untraced timing ratio 1.00 |
| overhead measured | traced span over untraced time per variant, and the IKET-enabled but unprofiled build's timing |
| effect direction and size preserved | the traced span difference between arms matches the untraced one |
| no new spills | `STACK 0`, `LOCAL 0` in the enabled build (`sass_inventory.py`) |
| outputs unchanged | bitwise equal outputs across original, stripped, enabled and traced runs |
| distributions | every interval over all CTAs and iterations, median with p20 and p80, never one CTA |
| first iteration apart | persistent CTAs' first item reported separately from steady state |
| separate runs | ncu and IKET never in the same process |

An effect smaller than the per-variant overhead difference cannot be ranked from traces. In the worked
example a 1.3% advantage reversed sign under tracing, while a 10% one was preserved.

## Pipeline

One `intra_kernel_events.py` run per trace, then every analysis reads the tables together (the DSv4 study's
marker names, with consumer warpgroups on warps 0-7 and the producer on warps 8-11):

```
S=<skill>/scripts
uv run --script $S/intra_kernel_events.py RUN/iket_pid_*.trace.json --variant np_tma \
    --roles consumer0:0-3,consumer1:4-7,producer:8-11 --launches 1 2 --out ev/np_tma.csv.gz
uv run --script $S/intra_kernel_intervals.py ev/np_tma.csv.gz ev/np_tma_tcfirst.csv.gz \
    --interval q_wait=c_wait_q@w0:c_q_ready@w0 --interval k_wait=c_wait_k@w0:c_k_ready@w0 \
    --interval q_flight=q_issued@w0:c_q_ready@w0 --gate first_gemm=q_wait,k_wait \
    --sm-gaps --spans --crowding q_flight
uv run --script $S/intra_kernel_ab_figure.py timeline ev/np_tma.csv.gz ev/np_tma_tcfirst.csv.gz --out tl.png \
    --rep life=warp.start@w0:warp.end@w0 --anchor init_done@w0 --rows "warp 0=w0" --rows "producer=w8" \
    --span "Q wait=c_wait_q:c_q_ready:#d55e00" --span "K wait=c_wait_k:c_k_ready:#e69f00"
```

"Which wait gates the next step" is `--gate`: list the waits before that step as intervals, and the table
gives the share of samples each one was the longest. Keep the investigation's full interval set in its
`commands.sh` (or a wrapper script beside it) so every table regenerates. A trace that
`intra_kernel_events.py` cannot read only needs a converter to the same table: a Triton kernel storing
`%globaltimer` and `%smid` per program through `tl.inline_asm_elementwise` ran through
`intra_kernel_intervals.py` and `intra_kernel_ab_figure.py` unchanged.

## Traces explain, variants decide

From the sliding16k traces alone, moving a 4-byte tile-count load ahead of a 64 KiB TMA Q load looked worth
at most 0.1 µs per CTA: the delayed load gated the first GEMM in only 11% of CTAs. Run as a variant, it
recovered 86 µs of a 97 µs regression (about 0.7 µs per CTA). The per-CTA "which wait gated the next step"
view missed two second-order effects: the late load delayed the producer (and so the keys) behind the Q, and
the whole grid's Q loads bunched into convoys that made every Q load slower (`--crowding` shows this:
median 27 other CTAs issuing within ±250 ns, against 13 after the change). Use traces to rank candidate
explanations and design variants, then let untraced timing of the variants decide.

## Worked example: TMA versus `cp.async` for a Q tile

- Question: why did moving a 64 KiB Q tile load from `cp.async` to TMA cost 0.8 µs per CTA in a
  one-CTA-per-query kernel on the uniform sliding16k workload, but save time in its persistent version?
- Traces: in the non-persistent kernel the Q wait gated the first score GEMM, and the TMA Q took 2.0 µs to
  land against 1.1 µs for `cp.async`. In the persistent kernel the next Q is issued during the previous
  epilogue and lands before it is needed.
- Variants: splitting the TMA over 4 warps finished the issue sooner but did not land Q sooner.
  EVICT_FIRST made it worse. Waiting for the small tile-count load before issuing the TMA fixed it.
  Issuing that load first without waiting did not: the small load is delayed while the TMA is in flight,
  whatever the issue order.
- Commands: the investigation's `commands.sh` under `~/tmp/profiling/dsv4-cute-trace/`.

## Other languages

- Triton: Proton (`triton.profiler`) has intra-kernel instrumentation. Not yet verified here. A hand-rolled
  probe works: `tl.inline_asm_elementwise("mov.u64 $0, %globaltimer;", "=l", [], dtype=tl.int64,
  is_pure=False, pack=1)` returns the timer (and `"mov.u32 $0, %smid;"` with `"=r"`, `tl.int32` the SM), stored
  to a global buffer and written out as `intra_kernel_events.py`'s table.
- TileLang: IKET support landed upstream (TileLang PR #2515, merged 2026-07-12). prime-rl pins 0.1.12,
  which predates it.
- CUDA C++: hand-rolled probes writing `globaltimer` or `clock64` plus `%smid` into a global buffer, in the style of
  DeepGEMM's `deep_gemm/include/deep_gemm/common/probe.cuh`. Not tried here. `globaltimer` is
  GPU-wide (32 ns steps on H200), `clock64` is per SM and not comparable across SMs.
- Binary level, no source changes: NVBit-based tools and Xtrace. Not tried here.
