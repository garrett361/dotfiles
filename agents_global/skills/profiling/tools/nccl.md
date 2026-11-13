# NCCL collectives: rates, NIC choice and versions

Use this when a collective runs slower than its links allow, when a torch upgrade changes step time, or before trusting a per-GPU network rate in a model or a kernel floor.

## Measure the production pattern, all groups at once

Time collectives with the real group structure, and with every group the job runs concurrently running at once. A group timed alone can read well above the rate the same group gets in training (1.7x in the example below). Example (H100 nodes, 8 GPUs and 8 InfiniBand NICs, each GPU pair sharing two NICs on one PCIe switch; NCCL 2.30.7): FSDP under expert parallelism 8 shards expert weights over groups of one GPU per node, one group per local GPU index. One such group alone read 33 GB/s per GPU (stock settings); all eight at once read 19.6, because NCCL put both GPUs of each pair on the same NIC. Groups that contain whole nodes read full rate either way. `scripts/node_check.py --checks comm` runs a concurrent one-GPU-per-node all-gather (`rail_all_gather`) next to the solo one (`rail_all_gather_solo`); `scripts/nic_share_check.py` is the same test as a self-contained script for sharing or for comparing versions.

Collective buffers: make each rank's share a multiple of 64 elements. Unaligned shares at GPU counts that are not a power of two read all-gather and reduce-scatter about 2x low.

## Read which NIC each rank uses

`NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,NET` (add `NCCL_DEBUG_FILE=<dir>/%h.%p.log` for one file per process) prints the NIC table once per process (`NET/IB : Using [0]mlx5_0:1/IB [1]mlx5_1:1/IB ...`) and one line per channel and peer (`Channel 01/0 : 9[1] -> 1[1] [send] via NET/IB/1/GDRDMA`, where the number after `NET/IB/` indexes that table). Compare against `nvidia-smi topo -m`, where `PIX` marks a NIC on the GPU's own PCIe switch. Two GPUs whose concurrent groups name the same NIC share its bandwidth.

## The NCCL version is part of the arm

- torch wheels pin an NCCL wheel (`nvidia-nccl-cu12` or `nvidia-nccl-cu13`, in the wheel's Requires-Dist), so a torch upgrade is also an NCCL upgrade. Example: torch 2.13 pins NCCL 2.29.7; torch 2.14 and 2.15 pin 2.30.7, which cut the concurrent one-GPU-per-node rate above by 40%; NCCL 2.31.2's release notes fix it ("limiting consistent start-NIC selection to Blackwell systems with ConnectX-8").
- To isolate NCCL with torch fixed, put another build in a directory (`uv pip install --no-deps --target <dir> nvidia-nccl-cu13==<version>`) and run with `LD_PRELOAD=<dir>/nvidia/nccl/lib/libnccl.so.2`. torch's pip wheels load `libnccl.so.2` dynamically, so the preloaded one wins (a torch built with NCCL linked statically ignores it). For a lasting pin under uv, `[tool.uv] override-dependencies`.
- Record the version that actually loaded: the `NCCL version x.y.z` line of the INFO log, or `ncclGetVersion` through ctypes on `libnccl.so.2`. `torch.cuda.nccl.version()` reports the version torch was built against and ignores a preload.
- Read the release notes of every version between the two you compare; behavior changes can be documented only in the release that reverts them.

## Environment

- Clusters inject `NCCL_*` variables into every job (from the node image or Slurm prolog). Log `env | grep ^NCCL_` per run and treat it as part of the arm.
- Check a knob name against the installed library before using it (`strings libnccl.so.2 | grep NCCL_<NAME>`); unknown names are ignored silently, and defaults change between versions (check the env docs for the version you run).
- Workarounds are version-specific. Example: `NCCL_NET_FORCE_MERGE` (fusing each GPU pair's two NICs into one virtual NIC) plus `NCCL_IB_SPLIT_DATA_ON_QPS=1` recovered most of the rate on 2.30.7 and cut it by 27% on 2.29.7. Re-measure any NCCL setting after a version change.
