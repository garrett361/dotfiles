"""Per GPU on one node, all GPUs at once: SM clock, temperature, power and thermal slowdown under minutes of bf16 GEMMs.

Self-contained (standard library and torch) for pasting into a bad-node report (`../reporting/bad-nodes.md`). A short
node check can pass on a node whose cooling falls behind only after minutes of full load; this keeps every GPU busy for
--minutes while nvidia-smi samples each GPU every --interval-ms, then reports per-GPU statistics over the samples after
the first --warmup-s.

Usage, under torchrun --standalone on one node: thermal_check.py [--minutes 8] [--n 8192] [--interval-ms 500]
"""

import argparse
import datetime
import os
import socket
import statistics
import subprocess
import tempfile
import time

import torch
import torch.distributed as dist

FIELDS = "timestamp,index,clocks.sm,temperature.gpu,temperature.gpu.tlimit,power.draw,clocks_event_reasons.active"
THERMAL_BITS = 0x20 | 0x40
POWER_CAP_BIT = 0x4
COUNTERS = "clocks_event_reasons_counters.sw_thermal_slowdown,clocks_event_reasons_counters.hw_thermal_slowdown"


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def thermal_counters_s():
    out = subprocess.run(["nvidia-smi", f"--query-gpu=index,{COUNTERS}", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True).stdout
    rows = [line.split(",") for line in out.strip().splitlines()]
    return {int(r[0]): (float(r[1]) + float(r[2])) / 1e6 for r in rows}


def gemm_loop(a, b, seconds, warmup_s):
    n, block, rates = a.shape[0], 50, []
    start_time = time.time()
    while time.time() - start_time < seconds:
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(block):
            torch.mm(a, b)
        end.record()
        torch.cuda.synchronize()
        if time.time() - start_time > warmup_s:
            rates.append(2 * n**3 * block / (start.elapsed_time(end) * 1e-3) / 1e12)
    return statistics.median(rates)


def read_samples(path, warmup_s):
    by_gpu = {}
    with open(path) as f:
        rows = [[x.strip() for x in line.split(",")] for line in f if line.strip()]
    t0 = datetime.datetime.strptime(rows[0][0], "%Y/%m/%d %H:%M:%S.%f")
    for r in rows:
        if (datetime.datetime.strptime(r[0], "%Y/%m/%d %H:%M:%S.%f") - t0).total_seconds() < warmup_s:
            continue
        by_gpu.setdefault(int(r[1]), []).append((float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[6], 16)))
    return by_gpu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=8.0, help="minutes of back-to-back GEMMs on every GPU")
    parser.add_argument("--n", type=int, default=8192, help="square GEMM size")
    parser.add_argument("--interval-ms", type=int, default=500, help="nvidia-smi sampling interval")
    parser.add_argument("--warmup-s", type=float, default=60.0, help="seconds at the start left out of the statistics")
    parser.add_argument("--min-headroom", type=float, default=5.0,
                        help="flag GPUs that come within this many C of their temperature limit (T.Limit); default for "
                             "H100 SXM, which reports its slowdown point at -2 C headroom")
    parser.add_argument("--max-thermal-share", type=float, default=0.01,
                        help="flag GPUs with thermal slowdown active in more than this share of samples")
    parser.add_argument("--clock-gap", type=float, default=0.05,
                        help="flag GPUs whose median SM clock is this fraction below the node's median GPU")
    args = parser.parse_args()

    local_rank = int(os.environ["LOCAL_RANK"])
    if int(os.environ["WORLD_SIZE"]) != int(os.environ["LOCAL_WORLD_SIZE"]):
        raise SystemExit("run under torchrun --standalone on one node")
    device = torch.device("cuda", local_rank)
    torch.cuda.set_device(device)
    dist.init_process_group("nccl", device_id=device)
    a = torch.randn(args.n, args.n, dtype=torch.bfloat16, device=device)
    b = torch.randn(args.n, args.n, dtype=torch.bfloat16, device=device)
    for _ in range(5):
        torch.mm(a, b)
    torch.cuda.synchronize()

    sampler, log = None, None
    if local_rank == 0:
        counters_before = thermal_counters_s()
        log = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        sampler = subprocess.Popen(["nvidia-smi", f"--query-gpu={FIELDS}", "--format=csv,noheader,nounits",
                                    f"-lms={args.interval_ms}"], stdout=log)
        started = utc_now()
    dist.barrier()
    tflops = gemm_loop(a, b, args.minutes * 60, args.warmup_s)
    dist.barrier()

    mine = torch.tensor([local_rank, tflops], dtype=torch.float64, device=device)
    gathered = [torch.empty_like(mine) for _ in range(dist.get_world_size())]
    dist.all_gather(gathered, mine)
    if local_rank == 0:
        sampler.terminate()
        sampler.wait()
        log.close()
        ended = utc_now()
        counters_after = thermal_counters_s()
        by_gpu = read_samples(log.name, args.warmup_s)
        os.unlink(log.name)
        rate = {int(t[0]): t[1].item() for t in gathered}
        host = socket.gethostname().split(".")[0]
        stats = {}
        for gpu, rows in sorted(by_gpu.items()):
            clocks = [r[0] for r in rows]
            stats[gpu] = {
                "median": statistics.median(clocks),
                "min": min(clocks),
                "temp": max(r[1] for r in rows),
                "headroom": min(r[2] for r in rows),
                "power": statistics.median(r[3] for r in rows),
                "thermal": sum(1 for r in rows if r[4] & THERMAL_BITS) / len(rows),
                "cap": sum(1 for r in rows if r[4] & POWER_CAP_BIT) / len(rows),
                "counter": counters_after[gpu] - counters_before[gpu],
                "samples": len(rows),
            }
        node_median = statistics.median(s["median"] for s in stats.values())
        print(f"{host}: {torch.cuda.get_device_name(device)}, torch {torch.__version__}, {started} to {ended}")
        print(f"bf16 {args.n}^3 GEMMs back to back on every GPU for {args.minutes:g} min; nvidia-smi every "
              f"{args.interval_ms} ms; statistics over the samples after the first {args.warmup_s:g} s")
        print("headroom = least degrees C under the GPU's temperature limit (T.Limit, negative when over); thermal % = "
              "share of samples with SW or HW thermal slowdown active; power cap % = same for SW power cap; "
              "thermal s = seconds of thermal slowdown the GPU's own counters added during the run")
        print(f"{'gpu':>3} {'samples':>7} {'SM MHz med':>10} {'SM MHz min':>10} {'max C':>5} {'headroom C':>10} "
              f"{'power W med':>11} {'thermal %':>9} {'power cap %':>11} {'thermal s':>9} {'TFLOP/s med':>11}")
        flagged = []
        for gpu, s in stats.items():
            print(f"{gpu:>3} {s['samples']:>7} {s['median']:>10.0f} {s['min']:>10.0f} {s['temp']:>5.0f} "
                  f"{s['headroom']:>10.0f} {s['power']:>11.0f} {100 * s['thermal']:>9.1f} {100 * s['cap']:>11.1f} "
                  f"{s['counter']:>9.1f} {rate[gpu]:>11.0f}")
            if (s["headroom"] < args.min_headroom or s["thermal"] > args.max_thermal_share
                    or s["median"] < (1 - args.clock_gap) * node_median):
                flagged.append(gpu)
        verdict = (f"HOT or slow on GPUs {flagged} (under {args.min_headroom:g} C headroom, thermal slowdown in more "
                   f"than {100 * args.max_thermal_share:g}% of samples, or median SM clock more than "
                   f"{100 * args.clock_gap:g}% under the node's median GPU at {node_median:.0f} MHz)")
        print(f"{host}: " + (verdict if flagged else "OK"))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
