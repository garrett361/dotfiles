"""Measure, per GPU on two 8-GPU nodes, the NCCL send rate to the same GPU index on the other node and the median NVLink send rate to each other GPU on its own node.

Self-contained (standard library and torch) for pasting into a bad-node report (`../reporting/bad-nodes.md`).

Usage, under torchrun on exactly 2 nodes: node_pair_check.py [--mib 256] [--iters 10] [--warmup 3]
"""

import argparse
import os
import socket
import statistics

import torch
import torch.distributed as dist

CROSS_NODE_MIN_GBS = 30.0
HOST_BYTES = 64
NVLINK_MIN_GBS = 260.0


def exchange_gbs(send, recv, dst, src, warmup, iters, group=None):
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    elapsed_ms = []
    for i in range(warmup + iters):
        ops = [dist.P2POp(dist.isend, send, dst, group), dist.P2POp(dist.irecv, recv, src, group)]
        dist.barrier()
        torch.cuda.synchronize()
        start.record()
        for work in dist.batch_isend_irecv(ops):
            work.wait()
        end.record()
        torch.cuda.synchronize()
        if i >= warmup:
            elapsed_ms.append(start.elapsed_time(end))
    return send.numel() * send.element_size() / (statistics.median(elapsed_ms) * 1e-3) / 1e9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mib", type=int, default=256, help="bf16 message size per send, MiB")
    parser.add_argument("--iters", type=int, default=10, help="timed iterations per measurement; the median is reported")
    parser.add_argument("--warmup", type=int, default=3, help="untimed iterations before each measurement")
    args = parser.parse_args()

    local_rank, per_node = int(os.environ["LOCAL_RANK"]), int(os.environ["LOCAL_WORLD_SIZE"])
    if int(os.environ["WORLD_SIZE"]) != 2 * per_node:
        raise SystemExit("run under torchrun on exactly 2 nodes with the same GPU count on each")
    device = torch.device("cuda", local_rank)
    torch.cuda.set_device(device)
    dist.init_process_group("nccl", device_id=device)
    rank, world = dist.get_rank(), dist.get_world_size()
    node_first_rank = rank - local_rank
    node_groups = [dist.new_group(list(range(first, first + per_node))) for first in (0, per_node)]

    send = torch.ones(args.mib * 2**20 // 2, dtype=torch.bfloat16, device=device)
    recv = torch.empty_like(send)
    cross_node = exchange_gbs(send, recv, (rank + per_node) % world, (rank - per_node) % world, args.warmup, args.iters)
    nvlink_per_peer = [
        exchange_gbs(
            send,
            recv,
            node_first_rank + (local_rank + shift) % per_node,
            node_first_rank + (local_rank - shift) % per_node,
            args.warmup,
            args.iters,
            node_groups[rank // per_node],
        )
        for shift in range(1, per_node)
    ]
    nvlink_median = statistics.median(nvlink_per_peer)

    name = socket.gethostname().split(".")[0].encode()[:HOST_BYTES].ljust(HOST_BYTES)
    mine = torch.tensor(list(name) + [local_rank, cross_node, nvlink_median], dtype=torch.float64, device="cuda")
    gathered = [torch.empty_like(mine) for _ in range(world)]
    dist.all_gather(gathered, mine)
    rows = [(bytes(int(b) for b in t[:HOST_BYTES].tolist()).decode().strip(), int(t[HOST_BYTES]), t[HOST_BYTES + 1].item(),
             t[HOST_BYTES + 2].item()) for t in gathered]
    if rank == 0:
        nccl = torch.cuda.nccl.version()
        nccl = ".".join(map(str, nccl)) if isinstance(nccl, tuple) else str(nccl)
        print(f"NCCL {nccl}, torch {torch.__version__}, {args.mib} MiB bf16 per send, "
              f"median of {args.iters} iterations after {args.warmup} warmup")
        print("cross-node: GPU k sends to GPU k on the other node while receiving from it (GB/s per direction);")
        print("  both ends of a slow link read slow, so pair a suspect node with a known-good one")
        print(f"NVLink: median over the {per_node - 1} other GPUs on the same node, same exchange in a per-node communicator")
        print(f"flagged: cross-node below {CROSS_NODE_MIN_GBS:.0f} GB/s or NVLink below {NVLINK_MIN_GBS:.0f} GB/s")
        print(f"{'host':<32} {'gpu':>3} {'cross-node GB/s':>16} {'NVLink median GB/s':>19}")
        for host, gpu, cross, nvlink in rows:
            print(f"{host:<32} {gpu:>3} {cross:>16.1f} {nvlink:>19.1f}")
        for host in dict.fromkeys(row[0] for row in rows):
            mine = [row for row in rows if row[0] == host]
            slow_cross = [gpu for _, gpu, cross, _ in mine if cross < CROSS_NODE_MIN_GBS]
            slow_nvlink = [gpu for _, gpu, _, nvlink in mine if nvlink < NVLINK_MIN_GBS]
            problems = []
            if slow_cross:
                problems.append(f"cross-node below {CROSS_NODE_MIN_GBS:.0f} GB/s on GPUs {slow_cross}")
            if slow_nvlink:
                problems.append(f"NVLink below {NVLINK_MIN_GBS:.0f} GB/s on GPUs {slow_nvlink}")
            print(f"{host}: " + ("SLOW, " + "; ".join(problems) if problems else "OK"))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
