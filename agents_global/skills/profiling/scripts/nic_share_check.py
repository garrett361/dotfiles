"""Show that concurrent one-GPU-per-node NCCL groups share NICs on nodes where two GPUs sit on one PCIe switch.

Such groups appear when a job shards over the ranks with the same local rank on every node (for example FSDP of
expert weights with experts sharded inside each node), one group per local GPU index, all running at once. This times
a bf16 all-gather (1 GiB output) three ways and prints bus bandwidth per GPU:
  rail, all at once: every local rank all-gathers within its own group at the same time
  rail, 1 alone:     only local rank 0's group runs
  all ranks:         one all-gather over every GPU of every node
then a verdict: the first row below 0.8x the second means groups share NICs; compare NCCL or torch versions with
it (`tools/nccl.md`). Self-contained (standard library and torch), so it can be pasted into a report and run with
`uv run --no-project --with torch==<version> torchrun ...` on any cluster.

Usage, one task per node under torchrun: nic_share_check.py [--gib 1] [--iters 10]
"""

import argparse
import ctypes
import os

import torch
import torch.distributed as dist


def loaded_nccl_version() -> str:
    version = ctypes.c_int()
    ctypes.CDLL("libnccl.so.2").ncclGetVersion(ctypes.byref(version))
    major, rest = divmod(version.value, 10000)
    return f"{major}.{rest // 100}.{rest % 100}"


def bus_gbps(group, output, shard, warmup: int, iters: int, active: bool) -> float:
    size = dist.get_world_size(group)
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    times = []
    for i in range(warmup + iters):
        dist.barrier()
        torch.cuda.synchronize()
        start.record()
        if active:
            dist.all_gather_into_tensor(output, shard, group=group)
        end.record()
        torch.cuda.synchronize()
        if i >= warmup:
            times.append(start.elapsed_time(end) / 1000)
    slowest = torch.tensor(sorted(times)[len(times) // 2], device="cuda")
    dist.all_reduce(slowest, op=dist.ReduceOp.MAX)
    return output.numel() * output.element_size() * (size - 1) / size / slowest.item() / 1e9


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gib", type=float, default=1.0)
    parser.add_argument("--iters", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()

    local_rank = int(os.environ["LOCAL_RANK"])
    per_node = int(os.environ["LOCAL_WORLD_SIZE"])
    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl", device_id=torch.device("cuda", local_rank))
    nodes = dist.get_world_size() // per_node
    if nodes < 2:
        raise SystemExit("run under torchrun on at least 2 nodes")

    rail_groups = [dist.new_group([lr + per_node * n for n in range(nodes)]) for lr in range(per_node)]
    my_rail = rail_groups[local_rank]

    elements = int(args.gib * 2**30 / 2)
    rows = []
    for name, group, active in (
        ("rail, all at once", my_rail, True),
        ("rail, 1 alone", my_rail, local_rank == 0),
        ("all ranks", None, True),
    ):
        size = dist.get_world_size(group)
        output = torch.empty(elements // (size * 64) * (size * 64), dtype=torch.bfloat16, device="cuda")
        shard = torch.ones(output.numel() // size, dtype=torch.bfloat16, device="cuda")
        rows.append((name, size, bus_gbps(group, output, shard, args.warmup, args.iters, active)))

    if dist.get_rank() == 0:
        print(f"{torch.cuda.get_device_name()}, {nodes} nodes x {per_node} GPUs, {args.gib} GiB bf16 all-gather output, NCCL {loaded_nccl_version()}, torch {torch.__version__}")
        print("NCCL environment: " + (" ".join(f"{k}={v}" for k, v in sorted(os.environ.items()) if k.startswith("NCCL_"))
                                      or "none set"))
        for name, size, gbps in rows:
            print(f"  {name:<22} group of {size:>3}: {gbps:6.1f} GB/s bus bandwidth per GPU")
        concurrent, solo = rows[0][2], rows[1][2]
        print(f"verdict: {'SHARED NICs' if concurrent < 0.8 * solo else 'OK'} "
              f"(all at once {concurrent:.1f} vs alone {solo:.1f} GB/s, flag below 0.8x)")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
