# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "torch", "triton"]
# ///
"""Known-answer controls for `exposed_comm.py` and `triton_event_recorder.py`; exits nonzero if any check fails.

Runs small synthetic arms whose exposed communication is known by construction, analyzes them with the same
`exposed_comm.analyze` code that users run on real data, and prints a pass/fail table of measured vs expected values.
The kernel is one persistent tiled BF16 GEMM `out[m, n] = a[m, k] b[n, k]` whose first programs can act as a copy
producer: they copy `SUB`-row units of `src` into the GEMM's `a` operand and publish each unit with a CTA barrier plus
a gpu-scope release add on an int32 flag per M tile. GEMM programs claim every `num_gemm_programs`-th output tile
(M-tile major) and, before the first load, spin in every thread on a gpu-scope acquire load of the tile's flag inside
one asm block. (A Triton-level spin with a CTA-wide min reduction compiled the unrecorded build's K loop without the
uniform datapath, 109 vs 85 instructions, and any recorder probe restored it, so the recorded build ran 2 to 5% faster.)
The recorder logs tile_start, tile_ready and tile_end per tile and a unit range per copied unit.

Arms (labels) and checks:
  comm, comm late          the copy producer alone (all units at --copy-programs; late units at --late-programs)
  gemm full, gemm <P>      the GEMM alone on all SMs and on the P programs a fused arm leaves it
  gemm <P> ... binary      G_P for the fused arms: the fused kernel itself with no copy and its flags preset ready
                           (the wait code compiled in), so the wait code's fixed cost lands in (a), not in (b) or (c)
  serial                   copy kernel, then the GEMM kernel (separate launches): E = C, measured (b) = C, (c) = 0
  wait-all                 fused; every tile waits for all units before its first load: T - G_P = C, (b) = C
  no-comm                  fused; flags preset ready, producer programs copy nothing: (b) = flag polls only; also
                           reports T minus the plain GEMM's G_P (the wait code's fixed cost)
  overlap                  fused; only units of M tiles first needed in the last eighth of the tile order are
                           copied, so no tile waits: (b) = flag polls only, T = G_P, H_P = H_max
  recorder                 traced span vs CUDA-event time, recorded vs unrecorded time (< 1%), and the unrecorded
                           build has no timer reads in its PTX
  negative controls        a mutant of wait-all that skips the wait (its output check and (b) = C must fail) and the
                           overlap arm analyzed with the old "(b) = C for a direct arm" assumption ((b) = 0 must fail)
  clocks                   per-arm busy median SM clock from nvidia-smi logs; the run is INVALID (exit 3) when arms
                           differ by more than --clock-tol-mhz or any arm hits the SW power cap in over 5% of samples

Modes: default, one GPU, src is a local HBM buffer; `--peer`, two GPUs, src is the peer GPU's buffer read through a
torch symmetric-memory peer view (`torch.distributed._symmetric_memory`: empty, rendezvous, get_buffer). Default
sizes keep every arm below the power cap by idling the GPU (`torch.cuda._sleep`) for --idle times each launch's
time between launches. `--capped`: larger GEMM, no idle, back-to-back launches at the power cap, serial arm only;
checks whether the tool's clock normalization turns the serial arm's apparent hiding back into H about 0.

Tolerances: every time check allows NOISE_K times the root sum of squares of the involved labels' spread over
--rounds ABBA rounds (max minus min of the round medians) plus LAUNCH_FLOOR_MS for launch gaps the CUDA events see
but kernels do not; event-based (b) checks add EVENT_FLOOR_MS for the CUDA-event vs first-program-start offset and
POLL_FLOOR_US_PER_TILE per tile of the busiest GEMM program for the flag poll each tile pays even when data is ready
(measured about 0.4 us per tile here and in a production fused gather GEMM).

Exit codes: 0 all checks pass, 1 a check failed (or a negative control passed), 3 invalid run (arm clocks differ, or
with --capped the serial arm's raw H is itself within tolerance of 0, so the run cannot test the normalization).

Usage (one node with GPUs, any directory; --out-dir keeps events, clock logs and results.json):
  uv run --script exposed_comm_controls.py [--peer | --capped] [--out-dir DIR] [--rounds 3] [--idle 1.0]
"""

import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys

import torch
import triton
import triton.language as tl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exposed_comm  # noqa: E402
from gpu_clocks import read_log  # noqa: E402
from triton_event_recorder import EventRecorder, globaltimer, rec_close, rec_put  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_INVALID = 0, 1, 3
NOISE_K = 4.0
LAUNCH_FLOOR_MS = 0.010
EVENT_FLOOR_MS = 0.010
POLL_FLOOR_US_PER_TILE = 1.0
SPAN_TOL = 0.03
RECORDER_OVERHEAD_TOL = 0.01
POWER_CAP_SHARE_MAX = 0.05
EVENTS = {
    1: ("tile_start", "mark"),
    2: ("tile_ready", "mark"),
    3: ("tile_end", "mark"),
    4: ("unit", "start"),
    5: ("unit", "end"),
}


@triton.jit
def _spin_acquire_gpu(ptr, target):
    """Spin in every thread on a gpu-scope acquire load of the int32 at `ptr` until it is at least `target`."""
    tl.inline_asm_elementwise(
        "{ .reg .pred p; .reg .b32 v;\n"
        "SPIN:\n"
        " ld.global.acquire.gpu.b32 v, [$1];\n"
        " setp.lt.s32 p, v, $2;\n"
        " @p bra SPIN;\n"
        " mov.u32 $0, 0; }",
        "=r,l,r", [ptr, target], dtype=tl.int32, is_pure=False, pack=1,
    )


@triton.jit
def _controls_kernel(
    src_ptr,
    a_ptr,
    b_ptr,
    out_ptr,
    flag_ptr,
    unit_begin,
    unit_end,
    num_copy_programs,
    num_gemm_programs,
    rec_ptr,
    M: tl.constexpr,
    N: tl.constexpr,
    K: tl.constexpr,
    BLOCK_M: tl.constexpr,
    BLOCK_N: tl.constexpr,
    BLOCK_K: tl.constexpr,
    NUM_STAGES: tl.constexpr,
    SUB: tl.constexpr,
    BLOCK_WORDS: tl.constexpr,
    WAIT: tl.constexpr,
    RECORD: tl.constexpr,
    REC_CAP: tl.constexpr,
):
    """Copy units of `src` into `a` on programs below `num_copy_programs`; the rest run the waiting GEMM tiles."""
    pid = tl.program_id(0)
    NUM_M_TILES: tl.constexpr = M // BLOCK_M
    NUM_N_TILES: tl.constexpr = N // BLOCK_N
    if RECORD:
        rec = rec_ptr + pid.to(tl.int64) * (REC_CAP * 4)
        t_start = globaltimer()
    slot = 1
    if pid < num_copy_programs:
        ROW_WORDS: tl.constexpr = K // 2
        src_words = src_ptr.to(tl.pointer_type(tl.int32))
        dst_words = a_ptr.to(tl.pointer_type(tl.int32))
        for unit in range(unit_begin + pid, unit_end, num_copy_programs):
            if RECORD:
                slot = rec_put(rec, slot, REC_CAP, 4, unit)
            rows = unit.to(tl.int64) * SUB + tl.arange(0, SUB)
            for word_start in tl.range(0, ROW_WORDS, BLOCK_WORDS, num_stages=1):
                offs = rows[:, None] * ROW_WORDS + (word_start + tl.arange(0, BLOCK_WORDS))[None, :]
                values = tl.load(src_words + offs, cache_modifier=".cg")
                tl.store(dst_words + offs, values)
            tl.debug_barrier()
            if WAIT == 2:
                tl.atomic_add(flag_ptr + NUM_M_TILES, 1, sem="release", scope="gpu")
            else:
                tl.atomic_add(flag_ptr + unit * SUB // BLOCK_M, 1, sem="release", scope="gpu")
            if RECORD:
                slot = rec_put(rec, slot, REC_CAP, 5, unit)
    else:
        offs_m = tl.arange(0, BLOCK_M)
        offs_n = tl.arange(0, BLOCK_N)
        offs_k = tl.arange(0, BLOCK_K)
        a_offs = offs_m[:, None] * K + offs_k[None, :]
        b_offs = offs_n[:, None] * K + offs_k[None, :]
        out_offs = offs_m[:, None] * N + offs_n[None, :]
        for tile in range(pid - num_copy_programs, NUM_M_TILES * NUM_N_TILES, num_gemm_programs):
            tile_m = tile // NUM_N_TILES
            tile_n = tile % NUM_N_TILES
            if RECORD:
                slot = rec_put(rec, slot, REC_CAP, 1, tile)
            if WAIT == 1:
                _spin_acquire_gpu(flag_ptr + tile_m, BLOCK_M // SUB)
            elif WAIT == 2:
                _spin_acquire_gpu(flag_ptr + NUM_M_TILES, unit_end - unit_begin)
            if RECORD:
                slot = rec_put(rec, slot, REC_CAP, 2, tile)
            a_base = a_ptr + tile_m.to(tl.int64) * (BLOCK_M * K)
            b_base = b_ptr + tile_n.to(tl.int64) * (BLOCK_N * K)
            acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)
            for k0 in tl.range(0, K, BLOCK_K, num_stages=NUM_STAGES):
                a = tl.load(a_base + k0 + a_offs)
                b = tl.load(b_base + k0 + b_offs)
                acc = tl.dot(a, tl.trans(b), acc)
            out_base = out_ptr + tile_m.to(tl.int64) * (BLOCK_M * N) + tile_n * BLOCK_N
            tl.store(out_base + out_offs, acc.to(tl.bfloat16))
            if RECORD:
                slot = rec_put(rec, slot, REC_CAP, 3, tile)
    if RECORD:
        rec_close(rec, slot, t_start, globaltimer())


def slug(label):
    """Return the clock-log file slug `exposed_comm.py` uses for a label."""
    return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")


class ClockLogger:
    """One nvidia-smi CSV log per label at `<prefix>__<slug>.csv`, appended across rounds."""

    def __init__(self, prefix, gpu_ids):
        """Log the GPUs `gpu_ids` (UUIDs) into files under `prefix`."""
        self.prefix, self.gpu_ids, self.proc, self.file = prefix, gpu_ids, None, None

    def start(self, label):
        """Stop any running logger and start one for `label`."""
        self.stop()
        self.file = open(f"{self.prefix}__{slug(label)}.csv", "a")
        query = "timestamp,index,clocks.sm,power.draw,temperature.gpu,clocks_event_reasons.active"
        cmd = ["nvidia-smi", "-i", ",".join(self.gpu_ids), f"--query-gpu={query}", "--format=csv", "-lms", "100"]
        self.proc = subprocess.Popen(cmd, stdout=self.file, stderr=subprocess.DEVNULL)

    def stop(self):
        """Stop the running logger, if any."""
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()
            self.file.close()
            self.proc = self.file = None


def clock_stats(prefix, label, busy_watts):
    """Return (busy median SM MHz, share of busy samples with the SW power cap bit) for a label's log."""
    path = f"{prefix}__{slug(label)}.csv"
    busy = [s for s in read_log(path) if s["power"] > busy_watts] if os.path.exists(path) else []
    if not busy:
        return None, None
    return statistics.median(s["sm"] for s in busy), sum(1 for s in busy if s["reasons"] & 0x4) / len(busy)


class Controls:
    """Buffers, arm definitions, timing and event recording for one rank."""

    def __init__(self, args, rank, world, device):
        """Allocate operands, the copy source (local or a symmetric-memory peer view) and per-arm launch lists."""
        self.args, self.rank, self.world, self.device = args, rank, world, device
        self.M, self.N, self.K = args.m, args.n, args.k
        self.BM, self.BN, self.BK, self.SUB = 128, 128, 64, 64
        self.num_warps = 8
        self.sms = torch.cuda.get_device_properties(device).multi_processor_count
        M, N, K = self.M, self.N, self.K
        assert M % self.BM == 0 and N % self.BN == 0 and K % self.BK == 0 and self.BM % self.SUB == 0
        self.units = M // self.SUB
        self.m_tiles = M // self.BM
        if args.rec_cap is None:
            min_gemm_programs = self.sms - max(args.copy_programs, args.late_programs)
            tiles = self.m_tiles * (N // self.BN)
            args.rec_cap = 2 + max(3 * math.ceil(tiles / min_gemm_programs), 2 * math.ceil(self.units / args.late_programs))
        self.handle = None
        source_rank = rank
        if args.peer:
            import torch.distributed as dist
            import torch.distributed._symmetric_memory as symm_mem

            local = symm_mem.empty((M, K), dtype=torch.bfloat16, device=device)
            local.copy_(self.make_source(rank))
            self.handle = symm_mem.rendezvous(local, group=dist.group.WORLD)
            source_rank = (rank + 1) % world
            self.src = self.handle.get_buffer(source_rank, (M, K), torch.bfloat16)
            self.local_src = local
            self.handle.barrier(channel=0)
        else:
            self.src = self.make_source(rank)
        self.source = self.make_source(source_rank)
        gen = torch.Generator(device=device).manual_seed(1000 + rank)
        self.b = torch.randn((N, K), generator=gen, device=device, dtype=torch.bfloat16)
        self.a = torch.empty((M, K), device=device, dtype=torch.bfloat16)
        self.out = torch.empty((M, N), device=device, dtype=torch.bfloat16)
        self.ref = self.source @ self.b.T
        self.flags = torch.zeros(self.m_tiles + 1, dtype=torch.int32, device=device)
        self.define_arms()
        self.recorders = {}

    def make_source(self, rank):
        """Return the deterministic copy source data of `rank`."""
        gen = torch.Generator(device=self.device).manual_seed(rank)
        return torch.randn((self.M, self.K), generator=gen, device=self.device, dtype=torch.bfloat16)

    def define_arms(self):
        """Build {label: (launches, flag init, a init)}; a launch is (copy programs, GEMM programs, units, WAIT)."""
        sms, pc, pl = self.sms, self.args.copy_programs, self.args.late_programs
        all_units = (0, self.units)
        late_first_m_tile = (7 * self.m_tiles) // 8
        late_units = (late_first_m_tile * (self.BM // self.SUB), self.units)
        zeros = torch.zeros_like(self.flags)
        ready = torch.full_like(self.flags, self.BM // self.SUB)
        early_ready = zeros.clone()
        early_ready[:late_first_m_tile] = self.BM // self.SUB
        self.late_rows = late_first_m_tile * self.BM
        self.cap_label = f"gemm {sms - pc}"
        self.late_cap_label = f"gemm {sms - pl}"
        self.wait_all_cap_label = f"gemm {sms - pc} wait-all binary"
        self.late_wait_cap_label = f"gemm {sms - pl} per-tile wait binary"
        arms = {
            "comm": ([(pc, 0, all_units, 0)], zeros, "poison"),
            "gemm full": ([(0, sms, (0, 0), 0)], zeros, "data"),
            self.cap_label: ([(0, sms - pc, (0, 0), 0)], zeros, "data"),
            "serial": ([(pc, 0, all_units, 0), (0, sms, (0, 0), 0)], zeros, "poison"),
        }
        if not self.args.capped:
            arms |= {
                "comm late": ([(pl, 0, late_units, 0)], zeros, "poison late"),
                self.late_cap_label: ([(0, sms - pl, (0, 0), 0)], zeros, "data"),
                self.wait_all_cap_label: ([(pc, sms - pc, (0, 0), 2)], zeros, "data"),
                self.late_wait_cap_label: ([(pl, sms - pl, (0, 0), 1)], ready, "data"),
                "wait-all": ([(pc, sms - pc, all_units, 2)], zeros, "poison"),
                "no-comm": ([(pc, sms - pc, (0, 0), 1)], ready, "data"),
                "overlap": ([(pl, sms - pl, late_units, 1)], early_ready, "poison late"),
                "wait-all mutant (no wait)": ([(pc, sms - pc, all_units, 0)], zeros, "poison"),
            }
        self.arms = arms
        self.recorded = [label for label in ("serial", "wait-all", "no-comm", "overlap", "wait-all mutant (no wait)")
                         if label in arms]

    def launch(self, launch, rec=None):
        """Enqueue one kernel launch; `rec` is the recorder view for its programs or None."""
        copy_programs, gemm_programs, (unit_begin, unit_end), wait = launch
        _controls_kernel[(copy_programs + gemm_programs,)](
            self.src, self.a, self.b, self.out, self.flags, unit_begin, unit_end, copy_programs, gemm_programs,
            rec, M=self.M, N=self.N, K=self.K, BLOCK_M=self.BM, BLOCK_N=self.BN, BLOCK_K=self.BK, NUM_STAGES=4,
            SUB=self.SUB, BLOCK_WORDS=128, WAIT=wait, RECORD=rec is not None,
            REC_CAP=self.args.rec_cap if rec is not None else 1, num_warps=self.num_warps,
        )

    def iteration(self, label, record_index=None):
        """Enqueue every launch of one iteration of `label`, recording into slot `record_index` when given."""
        launches = self.arms[label][0]
        offset = 0
        for launch in launches:
            rec = None
            if record_index is not None:
                grid = launch[0] + launch[1]
                rec = self.recorders[label].launch(record_index)[offset : offset + grid]
                offset += grid
            self.launch(launch, rec)

    def prepare_a(self, how):
        """Fill `a` with data, NaN, or data with NaN in the late M tiles."""
        if how == "data":
            self.a.copy_(self.source)
        elif how == "poison":
            self.a.fill_(float("nan"))
        else:
            self.a.copy_(self.source)
            self.a[self.late_rows :].fill_(float("nan"))

    def check_output(self, label):
        """Run one launch from a poisoned state and return (ok, max relative error) of `out` (or `a`) vs reference."""
        launches, flags_init, how = self.arms[label]
        self.prepare_a(how)
        self.out.fill_(float("nan"))
        self.flags.copy_(flags_init)
        self.sync_ranks()
        self.iteration(label)
        torch.cuda.synchronize()
        if all(launch[1] == 0 for launch in launches):
            first = launches[0][2][0] * self.SUB
            got, want = self.a[first:].float(), self.source[first:].float()
        else:
            got, want = self.out.float(), self.ref.float()
        err = ((got - want).abs().max() / want.abs().max()).item()
        return bool(math.isfinite(err) and err < 2e-2), err

    def sync_ranks(self):
        """Enqueue a device-side barrier across ranks in peer mode."""
        if self.handle is not None:
            self.handle.barrier(channel=0)

    def time_label(self, label, record=False):
        """Return the median ms of `label` over a timed loop (idle-padded), recording the last launches if asked."""
        launches, flags_init, _ = self.arms[label]
        args = self.args
        if record and label not in self.recorders:
            programs = sum(launch[0] + launch[1] for launch in launches)
            self.recorders[label] = EventRecorder(args.rec_launches, programs, args.rec_cap, device=self.device)
        probe = []
        for _ in range(3):
            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            self.flags.copy_(flags_init)
            start.record()
            self.iteration(label)
            end.record()
            probe.append((start, end))
        torch.cuda.synchronize()
        per_iter = max(s.elapsed_time(e) for s, e in probe)
        idle_ms = args.idle * per_iter
        counts = torch.tensor(
            [max(10, int(1e3 * args.warmup_s / (per_iter + idle_ms))), max(50, int(1e3 * args.rep_s / (per_iter + idle_ms)))],
            device=self.device,
        )
        if self.world > 1:
            import torch.distributed as dist

            dist.all_reduce(counts, op=dist.ReduceOp.MAX)
        warm, rep = (int(v) for v in counts.tolist())
        cycles = int(idle_ms * 1e-3 * args.sleep_hz)
        events = [(torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)) for _ in range(rep)]
        for i in range(warm + rep):
            self.flags.copy_(flags_init)
            if cycles:
                torch.cuda._sleep(cycles)
            self.sync_ranks()
            timed = i >= warm
            if timed:
                events[i - warm][0].record()
            self.iteration(label, record_index=i if record else None)
            if timed:
                events[i - warm][1].record()
        torch.cuda.synchronize()
        return statistics.median(s.elapsed_time(e) for s, e in events)


def run_rank(rank, world, args, results_path):
    """Run every arm on one rank; rank 0 analyzes, prints the table and writes results.json."""
    if world > 1:
        import torch.distributed as dist

        torch.cuda.set_device(rank)
        dist.init_process_group("nccl", rank=rank, world_size=world, device_id=torch.device("cuda", rank))
    device = torch.device("cuda", rank)
    ctl = Controls(args, rank, world, device)
    out_dir = args.out_dir
    clock_prefix = os.path.join(out_dir, "clocks", "run")
    logger = None
    if rank == 0:
        os.makedirs(os.path.dirname(clock_prefix), exist_ok=True)
        os.makedirs(os.path.join(out_dir, "events"), exist_ok=True)
        for name in os.listdir(os.path.dirname(clock_prefix)):
            os.remove(os.path.join(os.path.dirname(clock_prefix), name))
        uuids = [str(torch.cuda.get_device_properties(d).uuid) for d in range(world)]
        logger = ClockLogger(clock_prefix, [u if u.startswith("GPU-") else f"GPU-{u}" for u in uuids])

    correctness = {label: ctl.check_output(label) for label in ctl.arms}
    labels = list(ctl.arms) + [f"{label} rec" for label in ctl.recorded]
    rounds = {label: [] for label in labels}
    for r in range(args.rounds):
        order = labels if r % 2 == 0 else labels[::-1]
        for label in order:
            if logger:
                logger.start(label)
            base = label.removesuffix(" rec")
            rounds[label].append(ctl.time_label(base, record=label.endswith(" rec")))
            if logger:
                logger.stop()
    for label in ctl.recorded:
        ctl.recorders[label].to_tidy(
            os.path.join(out_dir, "events", f"{slug(label)}_rank{rank}.csv.gz"),
            variant=label,
            events=EVENTS,
            roles=[(0, ctl.arms[label][0][0][0], "comm"), (ctl.arms[label][0][0][0], None, "gemm")],
        )
    ptx = {"on": 0, "off": 0}
    loops = {"on": [], "off": []}
    for cache in _controls_kernel.device_caches.values():
        for kernel in cache[0].values():
            key = "on" if "%globaltimer" in kernel.asm["ptx"] else "off"
            ptx[key] += 1
            loops[key].append(mma_loop_size(kernel.asm["cubin"]))
    local = {
        "rounds": rounds,
        "correctness": correctness,
        "ptx_variants": ptx,
        "mma_loops": loops,
    }
    gathered = [local]
    if world > 1:
        import torch.distributed as dist

        gathered = [None] * world
        dist.all_gather_object(gathered, local)
    if rank == 0:
        verdict = analyze_and_report(ctl, args, gathered, clock_prefix)
        with open(results_path, "w") as f:
            json.dump(verdict, f, indent=1)
    if world > 1:
        import torch.distributed as dist

        dist.barrier()
        dist.destroy_process_group()


def mma_loop_size(cubin):
    """Return (instructions, uniform-datapath instructions) of the innermost SASS loop holding an MMA, or None."""
    tool = os.path.join(os.path.dirname(triton.__file__), "backends", "nvidia", "bin", "cuobjdump")
    path = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"exposed_comm_controls_{os.getpid()}.cubin")
    with open(path, "wb") as f:
        f.write(cubin)
    try:
        sass = subprocess.run([tool, "-sass", path], capture_output=True, text=True).stdout
    except OSError:
        return None
    finally:
        os.remove(path)
    lines = [m.groups() for m in re.finditer(r"/\*([0-9a-f]{4,})\*/\s+([^;]*);", sass)]
    addresses = [int(a, 16) for a, _ in lines]
    best = None
    for i, (_, text) in enumerate(lines):
        target = re.search(r"\bBRA (0x[0-9a-f]+)", text)
        if target and int(target.group(1), 16) in addresses[:i]:
            body = [t for _, t in lines[addresses.index(int(target.group(1), 16)) : i + 1]]
            if any("MMA" in t for t in body) and (best is None or len(body) < len(best)):
                best = body
    return None if best is None else (len(best), sum(1 for t in best if re.match(r"(@!?U?P\w+ )?U[A-Z]", t)))


def analyze_and_report(ctl, args, per_rank, clock_prefix):
    """Combine ranks, run `exposed_comm.analyze`, evaluate every check, print the table; return the verdict dict."""
    labels = list(per_rank[0]["rounds"])
    nrounds = len(per_rank[0]["rounds"][labels[0]])
    round_max = {label: [max(rk["rounds"][label][i] for rk in per_rank) for i in range(nrounds)] for label in labels}
    times = {label: statistics.median(v) for label, v in round_max.items()}
    spread = {label: max(v) - min(v) for label, v in round_max.items()}

    def tol(*names, floor=LAUNCH_FLOOR_MS):
        return NOISE_K * math.sqrt(sum(spread[n] ** 2 for n in names)) + floor

    events_dir = os.path.join(args.out_dir, "events")
    ev = {label: os.path.join(events_dir, f"{slug(label)}_rank*.csv.gz") for label in ctl.recorded}
    cap, late_cap = ctl.cap_label, ctl.late_cap_label
    wait_all_cap, late_wait_cap = ctl.wait_all_cap_label, ctl.late_wait_cap_label
    specs = [f"serial|impl=serial|comm=comm|direct|events={ev['serial']}|recorded=serial rec"]
    if not args.capped:
        specs += [
            f"wait-all|impl=wait-all|gemm_cap={wait_all_cap}|comm=comm|events={ev['wait-all']}|recorded=wait-all rec",
            f"no-comm vs plain G_P|impl=no-comm|gemm_cap={cap}|comm=comm|events={ev['no-comm']}|recorded=no-comm rec",
            f"overlap|impl=overlap|gemm_cap={late_wait_cap}|comm=comm late|events={ev['overlap']}|recorded=overlap rec",
            f"overlap vs plain G_P|impl=overlap|gemm_cap={late_cap}|comm=comm late|events={ev['overlap']}",
            f"mutant|impl=wait-all mutant (no wait)|gemm_cap={cap}|comm=comm|events={ev['wait-all mutant (no wait)']}",
            f"overlap as direct|impl=overlap|gemm_cap={late_wait_cap}|comm=comm late|direct",
        ]
    arms = [exposed_comm.parse_arm(spec) for spec in specs]
    mhz = lambda label: exposed_comm.clock_mhz(clock_prefix, label, args.busy_watts)  # noqa: E731
    rows, details, clocks = exposed_comm.analyze(times, "comm", "gemm full", arms, mhz=mhz)
    row = {r["arm"]: r for r in rows}
    detail = {d["arm"]: d for d in details}
    norm = {k["arm"]: k for k in clocks}
    checks = []
    valid, why = True, []

    def check(name, measured, expected, tolerance, negative=False, unit="ms"):
        ok = measured is not None and abs(measured - expected) <= tolerance
        checks.append(
            {"check": name, "measured": measured, "expected": expected, "tol": tolerance, "unit": unit,
             "negative": negative, "pass": (not ok) if negative else ok, "raw_ok": ok}
        )

    def boolean(name, ok, measured="", negative=False):
        checks.append(
            {"check": name, "measured": measured, "expected": "", "tol": "", "unit": "", "negative": negative,
             "pass": (not ok) if negative else ok, "raw_ok": ok}
        )

    for label, results in per_rank[0]["correctness"].items():
        oks = [rk["correctness"][label][0] for rk in per_rank]
        errs = [rk["correctness"][label][1] for rk in per_rank]
        boolean(f"output matches reference: {label}", all(oks), f"max rel err {max(errs):.2e}",
                negative=label.startswith("wait-all mutant"))

    s = row["serial"]
    c_all = times["comm"]
    tiles = (ctl.M // ctl.BM) * (ctl.N // ctl.BN)

    def poll(gemm_programs):
        return 1e-3 * POLL_FLOOR_US_PER_TILE * math.ceil(tiles / gemm_programs)

    pc_gemm, pl_gemm = ctl.sms - args.copy_programs, ctl.sms - args.late_programs
    if args.capped:
        k = norm.get("serial")
        tol_h = tol("serial", "comm", "gemm full") / c_all
        check("capped serial: clock-normalized H = 0", k["H_norm"] if k else None, 0.0, tol_h, unit="")
        raw_ok = abs(s["H"]) <= tol_h
        checks.append({"check": "capped serial: raw H differs from 0 (the control can discriminate)",
                       "measured": s["H"], "expected": 0.0, "tol": tol_h, "unit": "", "negative": False,
                       "pass": True, "raw_ok": raw_ok})
        if raw_ok:
            valid = False
            why.append("raw H of the serial arm is within tolerance of 0, so this capped run cannot test the normalization")
    else:
        check("serial: E = C", s["E"], c_all, tol("serial", "comm", "gemm full"))
        check("serial: measured (b) = C", s["b"], c_all,
              tol("serial rec", "comm", floor=EVENT_FLOOR_MS + LAUNCH_FLOOR_MS + poll(ctl.sms)))
        check("serial: (c) = 0", s["c"], 0.0, tol("serial", "serial rec", "comm", "gemm full"))
        w = row["wait-all"]
        check("wait-all: T - G_P = C", w["T"] - w["G_P"], c_all, tol("wait-all", wait_all_cap, "comm"))
        check("wait-all: measured (b) = C", w["b"], c_all,
              tol("wait-all rec", "comm", floor=EVENT_FLOOR_MS + LAUNCH_FLOOR_MS + poll(pc_gemm)))
        n = row["no-comm vs plain G_P"]
        check("no-comm: measured (b) = 0 (flag polls only)", n["b"], 0.0, tol("no-comm rec", floor=poll(pc_gemm)))
        checks.append({"check": "no-comm: wait-code cost T - G_P(plain GEMM) (reported)", "measured": n["E"] - n["a"],
                       "expected": 0.0, "tol": "", "unit": "ms", "negative": False, "pass": True, "raw_ok": True})
        o = row["overlap"]
        c_late = times["comm late"]
        check("overlap: measured (b) = 0 (flag polls only)", o["b"], 0.0, tol("overlap rec", floor=poll(pl_gemm)))
        check("overlap: T = G_P", o["T"], o["G_P"], tol("overlap", late_wait_cap))
        check("overlap: H_P = H_max", o["H_P"], o["H_max"], tol("overlap", late_wait_cap) / c_late, unit="")
        boolean("overlap: comm shorter than GEMM (C < G_full / 2)", c_late < times["gemm full"] / 2,
                f"C {c_late:.3f} G_full {times['gemm full']:.3f}")
        m = row["mutant"]
        check("negative: mutant measured (b) = C", m["b"], c_all,
              tol("wait-all mutant (no wait) rec", "comm", floor=EVENT_FLOOR_MS + LAUNCH_FLOOR_MS + poll(pc_gemm)),
              negative=True)
        d = row["overlap as direct"]
        check("negative: overlap with old direct (b) = C: (b) = 0", d["b"], 0.0,
              tol("overlap rec", floor=poll(pl_gemm)), negative=True)
    for label in ctl.recorded:
        if label.startswith("wait-all mutant"):
            continue
        name = {"wait-all": "wait-all", "no-comm": "no-comm vs plain G_P", "overlap": "overlap", "serial": "serial"}[label]
        if name not in detail:
            continue
        span = detail[name]["span"]
        check(f"recorder: {label} traced span / CUDA-event time = 1", span / times[f"{label} rec"], 1.0, SPAN_TOL, unit="")
        check(f"recorder: {label} recorded / unrecorded time = 1", times[f"{label} rec"] / times[label], 1.0,
              max(RECORDER_OVERHEAD_TOL, NOISE_K * math.hypot(spread[label], spread[f"{label} rec"]) / times[label]),
              unit="")
    variants = per_rank[0]["ptx_variants"]
    boolean("recorder: unrecorded builds have no %globaltimer in PTX", variants.get("off", 0) > 0,
            f"{variants.get('off', 0)} builds without, {variants.get('on', 0)} with timer reads")
    loops = per_rank[0]["mma_loops"]
    loop_text = "; ".join(f"{key} {sorted(set(map(tuple, v)) if None not in v else v)}" for key, v in loops.items())
    checks.append({"check": "recorder: MMA loop SASS (instructions, uniform) per build, off vs on (reported)",
                   "measured": loop_text, "expected": "", "tol": "", "unit": "", "negative": False, "pass": True,
                   "raw_ok": True})

    clock_rows = {}
    for label in labels:
        clock_rows[label] = clock_stats(clock_prefix, label, args.busy_watts)
    if not args.capped:
        meds = [v[0] for v in clock_rows.values() if v[0] is not None]
        missing = [label for label, v in clock_rows.items() if v[0] is None]
        if missing:
            valid = False
            why.append(f"no busy clock samples for {missing}")
        if meds and max(meds) - min(meds) > args.clock_tol_mhz:
            valid = False
            why.append(f"arm clocks span {min(meds):.0f}..{max(meds):.0f} MHz > {args.clock_tol_mhz} MHz")
        capped = [label for label, v in clock_rows.items() if v[1] is not None and v[1] > POWER_CAP_SHARE_MAX]
        if capped:
            valid = False
            why.append(f"SW power cap in > {POWER_CAP_SHARE_MAX:.0%} of busy samples: {capped}")

    print_report(ctl, args, times, spread, rows, details, clocks, checks, clock_rows, valid, why)
    failed = [c for c in checks if not c["pass"]]
    code = EXIT_INVALID if not valid else (EXIT_FAIL if failed else EXIT_PASS)
    return {"exit": code, "times": times, "spread": spread, "rows": rows, "details": details, "clocks": clocks,
            "checks": checks, "clock_rows": clock_rows, "valid": valid, "why": why}


def fmt(value, unit):
    """Format a check value."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.3f}" if unit == "ms" else f"{value:.4f}"
    return str(value)


def print_report(ctl, args, times, spread, rows, details, clocks, checks, clock_rows, valid, why):
    """Print timings, the exposed-comm table, clocks and the check table."""
    mode = "peer (2 GPUs)" if args.peer else "local (1 GPU)"
    print(f"\n## exposed_comm controls: {mode}{', capped' if args.capped else ''}; M={ctl.M} N={ctl.N} K={ctl.K}, "
          f"{ctl.sms} SMs, copy programs {args.copy_programs}, late programs {args.late_programs}, idle {args.idle}\n")
    print("| label | median ms (max over ranks) | spread over rounds ms | busy median SM MHz | SW power cap share |")
    print("|---|---:|---:|---:|---:|")
    for label, value in times.items():
        f, share = clock_rows.get(label, (None, None))
        print(f"| {label} | {value:.4f} | {spread[label]:.4f} | {f if f is None else round(f)} | "
              f"{'-' if share is None else f'{100 * share:.0f}%'} |")
    print("\n| arm | C | G_full | G_P | T | E | (a) | (b) | (b) source | (c) | H | H_P | H_max |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|")
    for r in rows:
        cells = [r["arm"]] + [f"{r[k]:.4f}" if r[k] is not None else "-" for k in ("C", "G_full", "G_P", "T", "E", "a", "b")]
        cells += [r["b_source"], f"{r['c']:.4f}" if r["c"] is not None else "-"]
        cells += [f"{100 * r[k]:.1f}%" for k in ("H", "H_P", "H_max")]
        print("| " + " | ".join(cells) + " |")
    if clocks:
        print("\n| arm | MHz G_full | MHz T | T norm | E norm | H norm |")
        print("|---|---:|---:|---:|---:|---:|")
        for k in clocks:
            print(f"| {k['arm']} | {k['f_ref']:.0f} | {k['f_T']:.0f} | {k['T_norm']:.4f} | {k['E_norm']:.4f} | "
                  f"{100 * k['H_norm']:.1f}% |")
    if details:
        print("\n| arm | launches | span ms | wait last ms | start delay last ms | wait mean ms | first-tile wait us |")
        print("|---|---:|---:|---:|---:|---:|---:|")
        for d in details:
            print(f"| {d['arm']} | {d['launches']} | {d['span']:.4f} | {d['b_last']:.4f} | {d['pre_last']:.4f} | "
                  f"{d['b_mean']:.4f} | {d['first_wait_us']:.1f} |")
    print("\n| check | measured | expected | tolerance | result |")
    print("|---|---:|---:|---:|---|")
    for c in checks:
        if c["negative"]:
            result = "PASS (negative control: failed as expected)" if c["pass"] else "FAIL (negative control passed)"
        else:
            result = "PASS" if c["pass"] else "FAIL"
        print(f"| {c['check']} | {fmt(c['measured'], c['unit'])} | {fmt(c['expected'], c['unit'])} | "
              f"{fmt(c['tol'], c['unit'])} | {result} |")
    failed = [c for c in checks if not c["pass"]]
    if not valid:
        print(f"\nINVALID run (exit {EXIT_INVALID}): " + "; ".join(why))
    elif failed:
        print(f"\nFAIL (exit {EXIT_FAIL}): {len(failed)} of {len(checks)} checks failed")
    else:
        print(f"\nPASS (exit {EXIT_PASS}): {len(checks)} checks")


def spawn_rank(rank, world, args, results_path, port):
    """Process entry point for one peer-mode rank."""
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT=str(port))
    run_rank(rank, world, args, results_path)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--peer", action="store_true", help="two GPUs, copy source on the peer GPU")
    p.add_argument("--capped", action="store_true", help="power-capped sizes, no idle, serial arm only")
    p.add_argument("--out-dir", default="exposed_comm_controls_out")
    p.add_argument("--m", type=int, default=32768)
    p.add_argument("--n", type=int)
    p.add_argument("--k", type=int, default=4096)
    p.add_argument("--copy-programs", type=int, help="default 16, or 8 with --capped")
    p.add_argument("--late-programs", type=int, help="default 4, or 8 with --peer (peer reads are slower per SM)")
    p.add_argument("--idle", type=float, help="idle time per launch, as a multiple of the launch time")
    p.add_argument("--rounds", type=int, help="default 3, or 5 with --capped")
    p.add_argument("--warmup-s", type=float)
    p.add_argument("--rep-s", type=float, default=1.0)
    p.add_argument("--sleep-hz", type=float, default=1.98e9, help="cycles per second assumed by torch.cuda._sleep")
    p.add_argument("--busy-watts", type=float, default=100.0)
    p.add_argument("--clock-tol-mhz", type=float, default=30.0)
    p.add_argument("--rec-launches", type=int, default=16)
    p.add_argument("--rec-cap", type=int, help="events per program; default fits every arm")
    args = p.parse_args()
    args.n = args.n or (4096 if args.capped else 1536)
    args.idle = args.idle if args.idle is not None else (0.0 if args.capped else 1.0)
    args.warmup_s = args.warmup_s if args.warmup_s is not None else (3.0 if args.capped else 1.0)
    args.copy_programs = args.copy_programs or (8 if args.capped else 16)
    args.rounds = args.rounds or (5 if args.capped else 3)
    args.late_programs = args.late_programs or (8 if args.peer else 4)
    os.makedirs(args.out_dir, exist_ok=True)
    results_path = os.path.join(args.out_dir, "results.json")
    if os.path.exists(results_path):
        os.remove(results_path)
    if args.peer:
        import torch.multiprocessing as mp

        port = 29500 + os.getpid() % 1000
        mp.spawn(spawn_rank, args=(2, args, results_path, port), nprocs=2, join=True)
    else:
        run_rank(0, 1, args, results_path)
    with open(results_path) as f:
        sys.exit(json.load(f)["exit"])


if __name__ == "__main__":
    main()
