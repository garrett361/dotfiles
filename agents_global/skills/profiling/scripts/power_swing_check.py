"""Per GPU, every GPU on one or more nodes at once: the hardware power-brake counter under a training-like load cycle.

Self-contained (standard library and torch) for pasting into a bad-node report (`../reporting/bad-nodes.md`). A node
whose power brake fires under training but not under `gemm_brake_check.py` may react to how power swings rather than to
its level: training repeats bursts of matrix multiplies and short idle or communication waits at a step cadence, on
every GPU at once. Each step here starts on every GPU together (a barrier), runs bf16 GEMMs for about --busy-ms, optionally
runs collectives (--comm: `a2a` is an all-to-all inside each node, `allgather` an all-gather over every rank, so across
nodes when there are several), and then idles for --idle-ms. With --overlap the collectives run on a second stream beside
the GEMMs instead of after them. The run lasts --seconds; the counter is read on every GPU before and after.

Per GPU it prints the brake time the counter added, the GEMM phase's median and maximum time per step, and the steps
whose GEMM phase took over --slow-factor times its median (a braked GPU slows to about a fifth of its clock for under a
second). A cycle that brakes a GPU on nearly every step leaves no fast median to compare with, so a GPU whose median
GEMM rate is under --tflops-min is flagged too. A healthy node adds 0.

Usage, under torchrun (--standalone on one node, or --nnodes N with a rendezvous): power_swing_check.py [--n 8192]
       [--busy-ms 200] [--idle-ms 100] [--seconds 120] [--comm none|a2a|allgather|both] [--comm-mb 256] [--overlap]
       [--slow-factor 1.5] [--tflops-min 550]
"""

import argparse
import os
import socket
import statistics
import subprocess
import time
from datetime import datetime, timezone

import torch
import torch.distributed as dist

HOST_BYTES = 64


def brake_us(uuid):
    out = subprocess.run(["nvidia-smi", "-i", uuid, "--query-gpu=clocks_event_reasons_counters.hw_power_brake_slowdown",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
    return float(out) if out.replace(".", "", 1).isdigit() else -1.0


def utc_now():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=8192, help="square GEMM size")
    parser.add_argument("--busy-ms", type=float, default=200.0, help="target GEMM time per step")
    parser.add_argument("--idle-ms", type=float, default=100.0, help="host-side idle time per step after the work")
    parser.add_argument("--seconds", type=float, default=120.0, help="length of the run")
    parser.add_argument("--comm", choices=["none", "a2a", "allgather", "both"], default="none",
                        help="collectives per step: all-to-all inside each node, all-gather over every rank, or both")
    parser.add_argument("--comm-mb", type=float, default=256.0, help="MiB each rank sends per collective per step")
    parser.add_argument("--overlap", action="store_true", help="run the collectives on a second stream beside the GEMMs")
    parser.add_argument("--slow-factor", type=float, default=1.5,
                        help="a step is slow when its GEMM phase takes over this many times the GPU's median")
    parser.add_argument("--tflops-min", type=float, default=550.0,
                        help="flag GPUs whose median GEMM rate is below this TFLOP/s (default for H100 SXM bf16)")
    args = parser.parse_args()

    local_rank, local_world = int(os.environ["LOCAL_RANK"]), int(os.environ["LOCAL_WORLD_SIZE"])
    device = torch.device("cuda", local_rank)
    torch.cuda.set_device(device)
    dist.init_process_group("nccl", device_id=device)
    world, rank = dist.get_world_size(), dist.get_rank()
    node_group, _ = dist.new_subgroups(local_world)

    a = torch.randn(args.n, args.n, dtype=torch.bfloat16, device=device)
    b = torch.randn(args.n, args.n, dtype=torch.bfloat16, device=device)
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    for _ in range(5):
        torch.mm(a, b)
    start.record()
    for _ in range(20):
        torch.mm(a, b)
    end.record()
    torch.cuda.synchronize()
    calls = torch.tensor([max(1, round(args.busy_ms / (start.elapsed_time(end) / 20)))], device=device)
    dist.all_reduce(calls, op=dist.ReduceOp.MIN)
    calls = int(calls.item())

    elements = int(args.comm_mb * 2**20 / 2) // local_world * local_world
    a2a_in = torch.randn(elements, dtype=torch.bfloat16, device=device)
    a2a_out = torch.empty_like(a2a_in)
    ag_in = torch.randn(elements // world, dtype=torch.bfloat16, device=device)
    ag_out = torch.empty(elements // world * world, dtype=torch.bfloat16, device=device)
    comm_stream = torch.cuda.Stream(device=device) if args.overlap else torch.cuda.current_stream(device)

    def collectives():
        with torch.cuda.stream(comm_stream):
            if args.comm in ("a2a", "both"):
                dist.all_to_all_single(a2a_out, a2a_in, group=node_group)
            if args.comm in ("allgather", "both"):
                dist.all_gather_into_tensor(ag_out, ag_in)

    uuid = f"GPU-{torch.cuda.get_device_properties(device).uuid}"
    brake_start = brake_us(uuid)
    dist.barrier()
    first = utc_now()
    gemm_ms, step_ms = [], []
    deadline = time.time() + args.seconds
    while True:
        go = torch.tensor([float(time.time() < deadline)], device=device)
        dist.all_reduce(go, op=dist.ReduceOp.MIN)
        if go.item() == 0:
            break
        t0 = time.perf_counter()
        if args.overlap and args.comm != "none":
            comm_stream.wait_stream(torch.cuda.current_stream(device))
            collectives()
        start.record()
        for _ in range(calls):
            torch.mm(a, b)
        end.record()
        if args.comm != "none" and not args.overlap:
            collectives()
        torch.cuda.synchronize()
        gemm_ms.append(start.elapsed_time(end))
        step_ms.append((time.perf_counter() - t0) * 1e3)
        time.sleep(args.idle_ms / 1e3)
    last = utc_now()
    torch.cuda.synchronize()
    brake = brake_us(uuid)

    median = statistics.median(gemm_ms)
    slow = sum(t > args.slow_factor * median for t in gemm_ms)
    name = socket.gethostname().split(".")[0].encode()[:HOST_BYTES].ljust(HOST_BYTES)
    mine = torch.tensor(list(name) + [local_rank, brake - brake_start, brake, median, max(gemm_ms), slow, len(gemm_ms),
                                      statistics.median(step_ms), 2 * args.n**3 * calls / (median * 1e-3) / 1e12],
                        dtype=torch.float64, device=device)
    gathered = [torch.empty_like(mine) for _ in range(world)]
    dist.all_gather(gathered, mine)
    if rank == 0:
        overlap = ", overlapped with the GEMMs" if args.overlap else ""
        comm = "no collectives" if args.comm == "none" else f"{args.comm} of {args.comm_mb:g} MiB per rank per step{overlap}"
        print(f"{torch.cuda.get_device_name(device)}, torch {torch.__version__}, {world} GPUs, {first}-{last} UTC: "
              f"steps of {calls} bf16 {args.n}^3 GEMMs (about {args.busy_ms:g} ms), {comm}, then {args.idle_ms:g} ms idle, "
              f"for {args.seconds:g} s")
        print("brake added = hardware power-brake time the counter added during this run (healthy nodes add 0)")
        print(f"{'host':<32} {'gpu':>3} {'brake added us':>15} {'power brake us':>15} {'GEMM TFLOP/s':>12} "
              f"{'GEMM ms med':>11} {'GEMM ms max':>11} {'slow steps':>10} {'step ms med':>11}")
        braked = {}
        for t in gathered:
            host = bytes(int(x) for x in t[:HOST_BYTES].tolist()).decode().strip()
            gpu, added, total, med, worst, slow_steps, steps, step_med, tflops = t[HOST_BYTES:].tolist()
            print(f"{host:<32} {int(gpu):>3} {added:>15.0f} {total:>15.0f} {tflops:>12.0f} {med:>11.1f} {worst:>11.1f} "
                  f"{f'{int(slow_steps)}/{int(steps)}':>10} {step_med:>11.1f}")
            if added > 0 or slow_steps > 0 or tflops < args.tflops_min:
                braked.setdefault(host, []).append(int(gpu))
        print(f"slow steps = GEMM phase over {args.slow_factor:g}x the GPU's median; GEMM TFLOP/s = rate at the median step")
        hosts = sorted({bytes(int(x) for x in t[:HOST_BYTES].tolist()).decode().strip() for t in gathered})
        for host in hosts:
            print(f"{host}: " + (f"BRAKED or slow on GPUs {braked[host]} (brake added, slow steps, or GEMM rate below "
                                 f"{args.tflops_min:.0f} TFLOP/s)" if host in braked else "OK"))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
