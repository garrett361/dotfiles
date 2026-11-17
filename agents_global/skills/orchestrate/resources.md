# Compute and shared resources

Handing out compute is the orchestrator's job, not the agents'. You hold every allocation, give each stream a slice, keep the slices busy, and give compute back as soon as nothing needs it.

## Release what is not needed

Release an allocation as soon as no stream has a known next use for it: when its streams are terminal or parked, or a benchmark finishes with nothing queued. At round end, once the verification runs have finished, release everything the same turn. "Might need it later" is not a use; allocating again later costs less than holding idle machines others are waiting for. Keep it only while the user is discussing a run that would reuse it. The one exception: never cancel an allocation early just to start its queued successor sooner, since the freed machines go to others' pending jobs. Record each release in the ledger and say so in the status line.

## Holding and handing out

- You acquire every allocation, within the round's compute budget: a cap on machines held at once until the hard stop, recorded in the decisions file. Re-acquiring within the cap needs no new decision; growing it needs the user. Agents never start, renew or cancel an allocation.
- Hold one allocation per slice you may release on its own (each development machine, the timing node) and one for the multi-machine pool, sized to the largest queued run. Part of an allocation cannot be given back, and a multi-machine step spans only one allocation's machines.
- The registry (`state.md`) is the ledger: per allocation, its handle, its devices or machines, the owner of each slice, and its expiry.
- Size each slice by the stream's next measurement: a device or one machine for development and per-op work; the pool only for the runs that need several machines (end-to-end, scaling).
- Split a machine's devices among agents explicitly (which devices each owns); one owner runs whole-machine jobs, or you schedule windows for them and have the other agents stop by a stated time.
- Whole-machine and multi-machine runs (end-to-end benchmarks, acceptance checks) go through one queue you own, ordered by which result unblocks the most streams. A stream that needs such runs develops on its own slice like any other and submits each run to the queue; the queue's machines are lent to the agent that launches the run, for that run only.
- Lend compute by handover message under the brief's Compute rule (`brief.md`), never beyond the round's cap.

## Keeping compute busy

- At every checkpoint, compare the ledger with what is actually running and with what each agent says it needs or can hand back. Idle compute with time left goes to a stream that can use it (a second design, an audit, a queued benchmark, a stress run) or is released.
- When compute sits idle because no stream can use it, say so in the status line rather than inventing work.
- Renew before expiry only when the user granted it (record the grant); queue the successor on the same machines so agents keep their environment, and tell each agent the new handle when it starts.
- Never take resources other users' pending work needs, and never cancel others' jobs, except as the user's cluster rules explicitly allow.

## Slurm GPU clusters

- Hold each allocation with `salloc ... --no-shell`; agents run steps in it with `srun --jobid=<job> --overlap`, each pinned to its own `CUDA_VISIBLE_DEVICES` and its own `TRITON_CACHE_DIR`.
- Node-check every allocation before handing it out (the profiling skill's `scripts/node_check.py`) and replace failed nodes.
- When any stream needs timing runs, keep one dedicated timing node, given to one timing agent at a time; when its time limit expires, allocate the same node again with `--nodelist`.
- For a granted renewal, submit the successor before the running job ends with `--nodelist=<its nodes> --deadline=<hard stop> --time-min=<minutes>`: it starts on the same nodes when they free, and Slurm shortens its limit to fit the hard stop instead of dropping the job (`--deadline` alone removes a job that can no longer finish its full limit in time). Node-check it too.
- Release with `scancel <job>`, on your own jobs only.

Example: 8 machines, two development streams and one stream that needs 4-machine end-to-end runs. One allocation per stream's development machine (three), one timing node, and a 4-machine pool for the queue. When a development stream turns terminal, its machine takes single-machine queue work if any is waiting, else it is released.

More detail: the profiling skill's `tools/agents.md` ("Allocations and GPUs") and the user's cluster memories.
