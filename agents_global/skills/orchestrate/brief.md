# Briefs

Write one shared brief file for the round and point every agent at it; each agent's own brief (or prompt) then carries only its task, branch, resources and targets. Later waves get an addendum file that names what it replaces.

## Shared brief sections

- **Goal and why**: what the user wants, in their words, and what decision the results feed.
- **State**: what exists now, with numbers and their sources (files, commits, runs). Mark what is measured and what is estimated.
- **Prior work**: branches, PRs and reports to build on, teammates' open work included, found by searching first. Say what may be adopted (with attribution) and what must not be touched.
- **Rules**:
  - Style and repo conventions, by pointer (the repo's AGENTS.md or CLAUDE.md).
  - The rules every agent inherits from the user's global instructions, named explicitly because subagents may not load them, for example: no `git push`, PR or fork creation; no CPU- or memory-heavy work on a login node; no code comments (omit them and list each one left out, with its location, in the report); no em or en dashes in files.
  - Measure, don't avoid: changes that alter behavior or numerics are run and their effect reported; adoption is decided later.
  - The two-designs rule: before reporting anything blocked, build and measure at least two genuinely different designs and state the remaining barrier with numbers.
  - Dependencies: what may be cloned or patched locally; forks and pins of pushed revisions need the user.
- **Compute**: the slices the orchestrator hands each agent by message, "yours from the orchestrator's handover message until it reclaims them or <hard stop>, whichever is first". Word it by handover, never by clock time: permission checks read clock times literally and can refuse a later widening by message as escalation. The orchestrator holds, renews and releases every allocation; agents never start, renew or cancel one, and never touch other jobs.
- **Ownership**: which branch, worktree or files each agent owns (git rules in SKILL.md).
- **Checkpoints**: times or intervals, a three-line status (best result, current blocker, next step, including compute needed before the next checkpoint or compute it can hand back), and a progress file.
- **Report**: the stream's terminal state (SKILL.md) with evidence; before and after numbers against the named baseline; what remains, each piece marked fundamental (with its measurement) or implementation (with the next step and expected gain).

## Per-agent brief

Task and why; branch and parent; resources; target against a named baseline commit and config (an unnamed baseline gets measured against whatever is convenient); acceptance check; not-worth-it threshold (the smallest measured gain worth pursuing); known overheads to remove and at least one alternative design (a brief with only the goal gets the first design that works); budget: a wall-clock hard stop plus resource or round limits, which audits and competing designs count against; what it owns; who it hands results to (the integration stream, a benchmark queue).
