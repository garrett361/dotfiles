# Running a perf investigation with subagents

Lessons from coordinating implementation, correctness, tuning and timing subagents on one shared GPU cluster (a night-long Hopper kernel port, 8x H200 nodes). Read this before fanning out work that both edits code and measures it.

## Before any agent starts

- Record the environment once and hand it to every agent in one shared brief file: partition time limits (`scontrol show partition <p>`), driver and CUDA version on a compute node (login hosts may have no GPU or `nvidia-smi`), interpreter path, and which existing tests already fail on this hardware at the base commit. Without the baseline failure list, agents misattribute pre-existing failures to their change or waste time on them.
- Measure the hardware's reference points up front and put them in the brief: power-cap behavior (`tools/do-bench.md`, power cap), peer copy bandwidth per direction, and the vendor-library roofline for the op (for example `torch._grouped_mm` for grouped GEMMs). Every later number is read against these.
- Write the shared brief as a file (rules, how to run on GPUs, which GPUs each agent owns, ownership of files, report format) and point each agent prompt at it; prompts then carry only the task.

## Allocations and GPUs

- Hold one allocation without a shell (`salloc ... --no-shell`) and have every agent run steps in it with `srun --jobid=<job> --overlap`, each pinned to its own `CUDA_VISIBLE_DEVICES` and its own `TRITON_CACHE_DIR`.
- Hold a second, dedicated node for timing only, for the whole investigation, and give it to one timing agent at a time. A shared development node gave 2 to 25% spread per arm; the dedicated node gave under 0.5% drift across sessions. When its time limit expires, re-allocate the same node with `--nodelist`.

## Code ownership and freezing

- Implementation agents in one worktree must not commit, stash or reset; each owns a disjoint file set and lists every file it changed. The coordinator reviews and commits in conventional-commit chunks, so every timing arm maps to a commit.
- Freeze each arm for timing with `git archive <sha> | tar -x -C <dir>` and run it via `PYTHONPATH=<dir>` with the project's interpreter (an editable install is shadowed by `PYTHONPATH`); have the agent record `module.__file__` per arm. This avoids extra worktrees and lets tuning continue in the live tree while the frozen arm is timed.
- A test that compares built artifacts to the working tree races with any agent editing the tree; run it when no one is editing.

## What to ask of timing and tuning agents

- Timing agents: reuse the previous agent's cases files and flags verbatim (from `commands.sh`), rerun the previous arm in the same session to control for drift, log clocks, and append a new section to `NOTES.md` instead of rewriting.
- Tuning agents: time-box them, require a log of everything tried (including failures and why), keep a static config table, require determinism and bitwise equality with the reference where it held before, and treat their development-node numbers as candidates only; confirm on the timing node before claiming a result.
- Ask every agent for reusable findings in its report and append them to one findings file as reports arrive; fold that file into this skill at the end rather than editing the skill from several agents at once.
