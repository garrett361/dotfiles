# Reporting a bad node

Use this when `scripts/node_check.py` or a slow run singles out a node, and the admins (or teammates on the same cluster) need to act on it. The report has two parts: a short note to paste into a chat or ticket, and one shared page per node that holds the evidence and a reproducer anyone with cluster access can run.

## 1. Confirm before reporting

- Repeat the failing measurement. A single low reading is not a report: one rail can dip for minutes and recover, and a node can recover by the next day.
- Pair a network suspect with at least two different healthy partners, and show each partner reading normal with some other node. Both ends of a slow link read slow, so a pair alone cannot say which side is at fault.
- Rule out the measurement: run the same reproducer on a node that passed `scripts/node_check.py` the same hour, and keep it as the healthy reference in the page.
- Note what is history and what is live: counters such as the hardware power-brake time and lifetime ECC errors accumulate since the driver or GPU last reset, so report the measured slowdown as the finding and the counter as supporting evidence.

## 2. The reproducer

One command line, run from a login node, needing only cluster access and `uv`:

```
srun -p <partition> -N 2 -w <bad node>,<healthy node> --gres=gpu:8 --exclusive -t 10 bash -c 'uv run --no-project --python 3.12 --with torch==<version> torchrun --nnodes 2 --nproc-per-node 8 --rdzv-backend c10d --rdzv-endpoint <bad node>:29500 --rdzv-id check <script>.py'
```

- The script uses only the standard library and torch, and the page shows it inline with a copy button. Nothing refers to a repo, a virtual environment or a path in anyone's home directory.
- Starting points in `scripts/`: `node_pair_check.py` (per-GPU send rate to the same GPU on another node, and NVLink inside each node), `gemm_brake_check.py` (short against sustained GEMM rate, and the power-brake counter, one node), `nic_share_check.py` (NICs shared by concurrent one-GPU-per-node groups, `tools/nccl.md`). Each prints one table per GPU and a verdict line per node.
- Pitfalls these scripts avoid: `dist.all_gather_object` needs numpy, which a plain torch environment lacks, so gather results as tensors; NVLink rates measured through a communicator that spans several nodes read far low (fewer channels per peer), so measure inside a per-node communicator; and `torch.cuda.nccl.version()` reports the compiled-in NCCL, not the loaded one.
- Run the exact command on the bad node and a healthy partner before publishing, and paste the real output into the page. The first `uv` run downloads torch, which can take a while; say so in the page.

## 3. The page (one per node)

- A plain-language lede: what is wrong, on which GPUs, how much against healthy.
- A small table of the bad node against a healthy reference node, with units and the date.
- What was done: how it was found, partners tried, repeats, times in UTC.
- What to check: the specific hardware path (NIC port and cable, PCIe and GPUDirect RDMA path, NVLink and NVSwitch, power supplies and the power-brake signal).
- The reproducer command, its output, and the script.
- Have a second agent check every number on the page against the raw results before it is shared.

## 4. The note

- A heading with the date and the full node name, then a bold one-line title in plain language.
- The page's full URL directly under the title, so it is copied along with the note.
- Three to five short bullets: the problem and its size against healthy, how it was confirmed, when, and what to check.
- No commands, scripts or local paths in the note; those live in the page.

Keep the notes in one file the user can paste from. Ask the user where it should live and how they mark notes already sent; a single markdown file in their scratch directory works well.
