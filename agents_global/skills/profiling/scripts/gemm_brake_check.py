"""Per GPU on one node, all GPUs at once: short and sustained bf16 GEMM rates and the hardware power-brake counter.

Self-contained (standard library and torch) for pasting into a bad-node report (`../reporting/bad-nodes.md`).

Usage, under torchrun --standalone on one node: gemm_brake_check.py [--n 8192] [--calls 50] [--sustain-s 15]
"""

import argparse
import os
import socket
import statistics
import subprocess
import time

import torch
import torch.distributed as dist

HOST_BYTES = 64


def gemm_tflops(a, b, calls):
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    times = []
    for _ in range(calls):
        start.record()
        torch.mm(a, b)
        end.record()
        torch.cuda.synchronize()
        times.append(start.elapsed_time(end))
    n = a.shape[0]
    return 2 * n**3 / (statistics.median(times) * 1e-3) / 1e12


def sustained_tflops(a, b, seconds):
    n, block, rates = a.shape[0], 50, []
    deadline = time.time() + seconds
    while time.time() < deadline:
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(block):
            torch.mm(a, b)
        end.record()
        torch.cuda.synchronize()
        rates.append(2 * n**3 * block / (start.elapsed_time(end) * 1e-3) / 1e12)
    return statistics.median(rates[len(rates) // 2:])


def brake_us(uuid):
    out = subprocess.run(["nvidia-smi", "-i", uuid, "--query-gpu=clocks_event_reasons_counters.hw_power_brake_slowdown",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
    return float(out) if out.replace(".", "", 1).isdigit() else -1.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=8192, help="square GEMM size")
    parser.add_argument("--calls", type=int, default=50, help="short GEMM calls; the median is reported")
    parser.add_argument("--short-min", type=float, default=550.0,
                        help="flag GPUs below this short-burst TFLOP/s (default for H100 SXM bf16)")
    parser.add_argument("--sustain-s", type=float, default=15.0, help="seconds of back-to-back GEMMs for the sustained rate")
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
    dist.barrier()
    short = gemm_tflops(a, b, args.calls)
    dist.barrier()
    sustained = sustained_tflops(a, b, args.sustain_s)
    brake = brake_us(f"GPU-{torch.cuda.get_device_properties(device).uuid}")

    name = socket.gethostname().split(".")[0].encode()[:HOST_BYTES].ljust(HOST_BYTES)
    mine = torch.tensor(list(name) + [local_rank, short, sustained, brake], dtype=torch.float64, device=device)
    gathered = [torch.empty_like(mine) for _ in range(dist.get_world_size())]
    dist.all_gather(gathered, mine)
    if dist.get_rank() == 0:
        print(f"{torch.cuda.get_device_name(device)}, torch {torch.__version__}, bf16 {args.n}^3 GEMM on every GPU at once: short = median of {args.calls} calls, "
              f"sustained = median of 50-call blocks over the second half of {args.sustain_s:.0f} s")
        print("power brake = microseconds of hardware power-brake throttling since the driver started (healthy nodes read 0)")
        print(f"{'host':<32} {'gpu':>3} {'short TFLOP/s':>14} {'sustained TFLOP/s':>18} {'power brake us':>15}")
        slow = []
        for t in gathered:
            host = bytes(int(x) for x in t[:HOST_BYTES].tolist()).decode().strip()
            gpu, short, sustained, brake = int(t[HOST_BYTES]), *t[HOST_BYTES + 1:].tolist()
            print(f"{host:<32} {gpu:>3} {short:>14.0f} {sustained:>18.0f} {brake:>15.0f}")
            if short < args.short_min or brake > 0:
                slow.append(gpu)
        print(f"{host}: " + (f"SLOW or braked on GPUs {slow} (short below {args.short_min:.0f} TFLOP/s or brake above 0)" if slow else "OK"))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
