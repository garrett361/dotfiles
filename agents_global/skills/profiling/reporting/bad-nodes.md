# Reporting a bad node

Use this when `scripts/node_check.py` or a slow run singles out a node, and the admins (or teammates on the same cluster) need to act on it. The report has two parts: a short note to paste into a chat or ticket, and one shared page per node that holds the evidence and a reproducer anyone with cluster access can run.

## 1. Confirm before reporting

- Repeat the failing measurement. A single low reading is not a report: one rail can dip for minutes and recover, and a node can recover by the next day.
- Pair a network suspect with at least two different healthy partners, and show each partner reading normal with some other node. Both ends of a slow link read slow, so a pair alone cannot say which side is at fault.
- A thermal suspect (a hot GPU, thermal slowdown or a low clock in a run's clock log) can pass a short check, since cooling falls behind only after minutes at full power: reproduce under several minutes of load on every GPU at once while sampling clocks, temperatures and throttle reasons, and leave the warm-up out of the statistics. Judge closeness to the limit by the GPU's T.Limit headroom (nvidia-smi `temperature.gpu.tlimit`), not `temperature.gpu`: the limit acts on a hotter internal sensor, so one H100 reading 74 C sat 1 C from it while another reading 71 C sat 13 C away. Report only a GPU that throttles or runs slow under the load (`thermal_check.py`'s FAIL); a small margin alone (its WARN) is not a fault, since healthy H100s sat 4-12 C from the limit, so note it and recheck later instead of reporting it.
- Rule out the measurement: run the same reproducer on a node that passed `scripts/node_check.py` the same hour, and keep it as the healthy reference in the page.
- Note what is history and what is live: counters such as the hardware power-brake and thermal-slowdown times and lifetime ECC errors accumulate since the driver or GPU last reset, so report the measured slowdown as the finding and the counter as supporting evidence.

## 2. The reproducer

One command line, run from a login node, needing only cluster access and `uv`:

```
srun -p <partition> -N 2 -w <bad node>,<healthy node> --gres=gpu:<gpus per node> --exclusive -t 10 bash -c 'uv run --no-project --python 3.12 --with torch==<version> torchrun --nnodes 2 --nproc-per-node <gpus per node> --rdzv-backend c10d --rdzv-endpoint <bad node>:29500 --rdzv-id check <script>.py'
```

For a single-node check, `-N 1 -w <node>` and `torchrun --standalone --nproc-per-node <gpus per node>`. Save the script in a directory every node can read (a shared home or project filesystem), and run the command from there.

- The script uses only the standard library and torch, and the page shows it inline with a copy button. Nothing refers to a repo, a virtual environment or a path in anyone's home directory.
- Starting points in `scripts/`: `node_pair_check.py` (per-GPU send rate to the same GPU on another node, and NVLink inside each node), `gemm_brake_check.py` (short against sustained GEMM rate, and the power-brake counter, one node), `nic_share_check.py` (NICs shared by concurrent one-GPU-per-node groups, `tools/nccl.md`), `thermal_check.py` (minutes of GEMMs on every GPU while nvidia-smi samples SM clock, temperature, power and throttle reasons, one node), `power_swing_check.py` (the power-brake counter under a training-like cycle of GEMM bursts, optional collectives and short idle gaps on every GPU at once, one or more nodes; for a node braked in training whose `gemm_brake_check.py` passes). Each prints the GPU model, the versions it ran with, one row per GPU (or per group) and a verdict; thresholds are flags whose defaults are labeled for the hardware they suit.
- Pitfalls these scripts avoid: `dist.all_gather_object` needs numpy, which a plain torch environment lacks, so gather results as tensors; NVLink rates measured through a communicator that spans several nodes read far low (fewer channels per peer), so measure inside a per-node communicator; and `torch.cuda.nccl.version()` reports the compiled-in NCCL, not the loaded one.
- Run the exact command on the bad node and a healthy partner before publishing, and paste the real output into the page. The first `uv` run downloads torch, which can take a while; say so in the page.

## 3. The page (one per node)

The reader is an admin deciding what hardware to inspect. Everything above the reproducer fits one screen, about 250 words.

- A lede of one or two sentences: what is wrong, on which GPUs or ports, how much against healthy.
- A small table of the bad GPUs against a healthy reference node: the three or four measurements that show the fault, with units and the date. Name other GPUs on the node only when they also fail.
- What was done, in two or three bullets: how it was found in one sentence, the repeats with UTC times, the healthy reference and partners tried. Leave out the investigation behind it (job IDs, ranks, collective timings, swap tests, counter histories); it lives in the project's own notes.
- What to check: the specific hardware path (NIC port and cable, PCIe and GPUDirect RDMA path, NVLink and NVSwitch, power supplies and the power-brake signal, or for a hot GPU its cooling: fans, airflow, heatsink and thermal interface, and the BMC's thermal logs), with bus IDs or serials so the admin can find the part.
- The reproducer command, the bad node's real output, and the script folded in a collapsed block. The healthy node's numbers go in the table, not in a second output block.
- Have a second agent check every number on the page against the raw results before it is shared.

## 4. The note

- A heading with the date and the full node name, then a bold one-line title in plain language naming the GPUs or ports and the size of the problem.
- The page's full URL directly under the title, so it is copied along with the note.
- Three bullets of one sentence each, about 25 words: the problem against healthy with one pair of numbers; how and when it was confirmed (repeats, healthy reference, UTC date); what to check.
- Everything else lives on the page: the remaining measurements, each run's figures, counter histories, and how the node was found or what it did to a training run. A note of about 80 words is the target.
- No commands or scripts in the note; those live in the page.
- No paths only the user can read, in the note or on the page: nothing under their home directory (`~/...`, `/home/<user>/...`), no scratch or session directories, no job log locations. Readers are admins and teammates who cannot open them. This covers every later line too, such as a recheck or pass note appended to an existing section: state the result, the date and the job ID, and keep log locations in the project's own notes.

Keep the notes in one file the user can paste from. Ask the user where it should live and how they mark notes already sent; a single markdown file in their scratch directory works well.
