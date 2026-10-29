# /// script
# requires-python = ">=3.10"
# dependencies = ["torch", "triton"]
# ///
"""Per-program `%globaltimer` event recorder for Triton kernels, meant to be copied into a project as one file.

Writes the tidy event table of `intra_kernel_events.py`, so `intra_kernel_intervals.py`, `intra_kernel_ab_figure.py`
and `exposed_comm.py` read Triton kernels unchanged. Gate every call behind a `RECORD: tl.constexpr` so the
unrecorded build compiles to the original code, and measure the recorded build's overhead against it.

Buffer layout: int64 `[launches, programs, cap, 4]`. Slot 0 of each program is its header `(t_start, t_end, events,
smid)`, written by `rec_close`; slots `1..cap-1` hold `(t_ns, event_id << 32 | payload, 0, 0)`, the payload truncated
to int32. Events past `cap - 1` are dropped and counted in the header, so `to_tidy` warns about truncation instead of
reading garbage.

Kernel side (inside `@triton.jit` code; `rec` is the int64 buffer base for this launch, see `EventRecorder.launch`):
  if RECORD:
      rec = rec_ptr + tl.program_id(0).to(tl.int64) * (REC_CAP * 4)
      t_start = globaltimer()
      slot = 1
  ...
  if RECORD:
      slot = rec_put(rec, slot, REC_CAP, 1, tile)   # event 1 with payload `tile`
  ...
  if RECORD:
      rec_close(rec, slot, t_start, globaltimer())

Each `rec_put` is one volatile asm block in which thread 0 reads `%globaltimer` and makes one 16-byte store, and no
timer value flows back into Triton code. In a persistent GEMM, Triton-level stores or timer arithmetic per event moved
the time by 4%, a second store per event by 1.7%, this design by under 1% (`tools/exposed-comm.md`). Any probe still
changes the PTX, and ptxas can then compile the hot loop differently, so measure every kernel's recorded vs unrecorded
time. Record only where thread 0 runs. A probe orders after earlier control flow and earlier volatile asm, not after
outstanding loads: put it after a loop that consumes the awaited value (a flag spin) or after an instruction that waits
on the load, never right after an asynchronous issue. `%globaltimer` is GPU-wide (32 ns steps on H100/H200).

Host side:
  recorder = EventRecorder(launches=4, programs=grid, cap=256, device="cuda")
  kernel[grid](..., rec_ptr=recorder.launch(i), RECORD=True, REC_CAP=recorder.cap)   # i-th recorded launch
  recorder.to_tidy("ev.csv.gz", variant="fused", events={1: ("tile", "start"), 2: ("tile", "end")},
                   roles=[(0, 12, "gather"), (12, None, "gemm")])

Self-test on one GPU, from a project that has torch and triton:
  uv run --no-sync python triton_event_recorder.py
"""

import csv
import gzip
import sys

import torch
import triton
import triton.language as tl

COLUMNS = ("variant", "launch", "sm", "cta", "warp", "role", "event", "phase", "t_ns", "payload")


@triton.jit
def globaltimer():
    """Return the GPU-wide nanosecond timer."""
    return tl.inline_asm_elementwise("mov.u64 $0, %globaltimer;", "=l", [], dtype=tl.int64, is_pure=False, pack=1)


@triton.jit
def smid():
    """Return the id of the SM running this program."""
    return tl.inline_asm_elementwise("mov.u32 $0, %smid;", "=r", [], dtype=tl.int32, is_pure=False, pack=1)


@triton.jit
def rec_put(rec, slot, REC_CAP: tl.constexpr, event, payload):
    """Store `(now, event << 32 | int32 payload)` at `slot` from thread 0 if it fits and return the next slot."""
    tl.inline_asm_elementwise(
        "{ .reg .pred p, q; .reg .u32 tid; .reg .u64 t;\n"
        " mov.u32 tid, %tid.x; setp.eq.u32 p, tid, 0; setp.gt.s32 q, $2, 0; and.pred p, p, q;\n"
        " @p mov.u64 t, %globaltimer;\n"
        " @p st.global.v2.b64 [$1], {t, $3};\n"
        " mov.u32 $0, 0; }",
        "=r,l,r,l", [rec + slot * 4, REC_CAP - slot, (payload.to(tl.int64) & 0xFFFFFFFF) | (event << 32)],
        dtype=tl.int32, is_pure=False, pack=1)
    return slot + 1


@triton.jit
def rec_close(rec, slot, t_start, t_end):
    """Store the program header: start, end, event count (including dropped ones) and SM id."""
    tl.store(rec, t_start.to(tl.int64))
    tl.store(rec + 1, t_end.to(tl.int64))
    tl.store(rec + 2, (slot - 1).to(tl.int64))
    tl.store(rec + 3, smid().to(tl.int64))


class EventRecorder:
    """Device buffer for `launches` recorded launches of a grid of `programs`, `cap - 1` events per program."""

    def __init__(self, launches: int, programs: int, cap: int, device="cuda"):
        """Allocate the zeroed int64 `[launches, programs, cap, 4]` buffer."""
        self.launches, self.programs, self.cap = launches, programs, cap
        self.buffer = torch.zeros((launches, programs, cap, 4), dtype=torch.int64, device=device)

    def launch(self, index: int) -> torch.Tensor:
        """Return the buffer view to pass as `rec_ptr` for recorded launch `index` (taken modulo `launches`)."""
        return self.buffer[index % self.launches]

    def rows(self, variant: str, events: dict, roles: list, launches=None):
        """Yield tidy rows; `events` maps id to (name, phase), `roles` lists (first, end or None, role) program ranges."""
        data = self.buffer.cpu().tolist()
        truncated = 0
        for launch in launches if launches is not None else range(self.launches):
            headers = [data[launch][program][0] for program in range(self.programs)]
            starts = [h[0] for h in headers if h[0] > 0]
            if not starts:
                continue
            t0 = min(starts)
            for program in range(self.programs):
                t_start, t_end, count, sm = headers[program]
                if t_start == 0:
                    continue
                role = next((r for first, end, r in roles if first <= program and (end is None or program < end)), "")
                base = (variant, launch, sm, program, 0, role)
                yield (*base, "warp", "start", t_start - t0, "")
                stored = min(count, self.cap - 1)
                truncated += count - stored
                for slot in range(1, stored + 1):
                    t, packed, _, _ = data[launch][program][slot]
                    event, payload = packed >> 32, (packed & 0xFFFFFFFF) - ((packed & 0x80000000) << 1)
                    name, phase = events.get(event, (f"event{event}", "mark"))
                    yield (*base, name, phase, t - t0, payload)
                yield (*base, "warp", "end", t_end - t0, "")
        if truncated:
            print(f"warning: {truncated} events dropped past cap={self.cap}; raise cap", file=sys.stderr)

    def to_tidy(self, path: str, variant: str, events: dict, roles: list, launches=None):
        """Write the tidy event table (gzipped when `path` ends in .gz)."""
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "wt", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerows(self.rows(variant, events, roles, launches))


@triton.jit
def _selftest_kernel(x_ptr, n, rec_ptr, RECORD: tl.constexpr, REC_CAP: tl.constexpr, BLOCK: tl.constexpr):
    """Sum a strided slice per program, recording one start and end event per block."""
    pid = tl.program_id(0)
    if RECORD:
        rec = rec_ptr + pid.to(tl.int64) * (REC_CAP * 4)
        t_start = globaltimer()
        slot = 1
    acc = tl.zeros((BLOCK,), dtype=tl.float32)
    for start in range(pid * BLOCK, n, tl.num_programs(0) * BLOCK):
        if RECORD:
            slot = rec_put(rec, slot, REC_CAP, 1, start)
        offs = start + tl.arange(0, BLOCK)
        acc += tl.load(x_ptr + offs, mask=offs < n, other=0.0)
        if RECORD:
            slot = rec_put(rec, slot, REC_CAP, 2, tl.sum(acc).to(tl.int64) * 0 + start)
    tl.store(x_ptr + pid, tl.sum(acc))
    if RECORD:
        rec_close(rec, slot, t_start, globaltimer())


if __name__ == "__main__":
    x = torch.ones(1 << 22, device="cuda")
    recorder = EventRecorder(launches=2, programs=8, cap=1100)
    for i in range(2):
        _selftest_kernel[(8,)](x, x.numel(), recorder.launch(i), RECORD=True, REC_CAP=recorder.cap, BLOCK=1024)
    torch.cuda.synchronize()
    rows = list(recorder.rows("selftest", {1: ("block", "start"), 2: ("block", "end")}, [(0, None, "worker")]))
    blocks = [r for r in rows if r[6] == "block"]
    assert blocks and all(r[8] >= 0 for r in rows), rows[:4]
    print(f"{len(rows)} rows, {len(blocks)} block events, first {rows[:3]}")
