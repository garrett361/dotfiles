# Briefs

Write one shared brief file for the round and point every agent at it; each agent's own brief (or prompt) then carries only its task, branch, resources and targets. Later waves get an addendum file that names what it replaces. For a run of profiling and tuning agents, see also the profiling skill's `tools/agents.md`.

## Shared brief sections

- **Goal and why**: what the user wants, in their words, and what decision the results feed.
- **State**: what exists now, with numbers and their sources (files, commits, runs). Mark what is measured and what is estimated.
- **Prior work**: branches, PRs and reports to build on, including teammates' open work found by searching first. Say what may be adopted (with attribution) and what must not be touched.
- **Rules**:
  - Style and repo conventions, by pointer (the repo's AGENTS.md or CLAUDE.md).
  - The rules every agent inherits from the user's global instructions, named explicitly because subagents may not load them, for example: no `git push`, PR or fork creation; no CPU- or memory-heavy work on a login node; no code comments (omit them and list each one left out, with its location, in the report); no em or en dashes in files; only the orchestrator cancels jobs (`resources.md`).
  - Measure, don't avoid: changes that alter behavior or numerics are run and their effect reported; adoption is decided later.
  - The two-designs rule: before reporting anything blocked, build and measure at least two genuinely different designs and state the remaining barrier with numbers.
  - Dependencies: what may be cloned or patched locally; forks and pins of pushed revisions need the user.
- **Compute**: the slices the orchestrator hands each agent by message, "yours from the orchestrator's handover message until it reclaims them or <hard stop>, whichever is first"; the orchestrator holds, renews and releases every allocation; agents never start, renew or cancel one, and never touch other jobs.
- **Ownership**: which branch, worktree or files each agent owns; one writer per branch.
- **Checkpoints**: times or intervals, a three-line status (best result, current blocker, next step, including compute needed before the next checkpoint or compute it can hand back), and a progress file.
- **Report**: the stream's state in the orchestrator's terms (done, proven blocker, not worth it, escalated, out of time) with evidence; before and after numbers against the named baseline; what remains, each piece marked fundamental (with its measurement) or implementation (with the next step and expected gain).

## Per-agent brief

Task and why; branch and parent; resources; target, acceptance check and not-worth-it threshold (the smallest measured gain worth pursuing); known overheads to remove and design candidates to try; budget and hard stop; what it owns; who it hands results to (the integration stream, a benchmark queue).

## Pitfalls

- A target stated without its baseline gets measured against whatever is convenient. Name the baseline commit and config.
- A brief that lists only the goal gets the first design that works. List the known overheads and at least one alternative design up front.
- Resources described by clock time instead of the handover are read literally by permission checks; widening them later by message can be refused as escalation.
