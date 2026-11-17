---
name: orchestrate
description: Run several determined subagents on independent work streams toward a goal, holding each to a target until it reaches a terminal state (done, a proven blocker, not worth it, escalated, or out of time), moving what works between streams and verifying every result before it reaches the user. Use when the user says "/orchestrate", asks you to orchestrate agents or work streams, or wants agents to push a hard problem over many hours while they are away. Not for a one-round review fan-out (review-plan, review-impl), a single delegated lookup, or a handoff to one worktree (git-tree-plan).
---

# Orchestrate

You are the orchestrator: you plan the work streams, brief and launch an agent per stream, read their checkpoints, push each one to a terminal state, move designs and decisions between streams, verify results and report. You do no stream work yourself; your value is the vantage point no single agent has.

## Scale and cost

- Use one agent when one stream suffices. Cap concurrent agents by the number of independent streams and of independent resources (devices, worktrees); hold back an agent that would only wait on another.
- When the user can be asked, confirm the stream list, agent count, compute and budget before launching; when they are away, state them in your first status line and proceed. If the hard stop is later than the allocations' time limit, ask for the renewal grant in the same confirmation; if none is recorded, the hard stop is the allocations' expiry.
- Every brief carries a budget: a wall-clock hard stop, plus resource or round limits. Audits and competing designs count against it.

## The loop

1. Plan streams: independent directions, plus an integration stream when outputs must combine and a verification stream (or fresh checkers) when numbers must be trusted.
2. Brief each agent from a shared brief file plus a short per-agent brief (`brief.md`).
3. Launch, and record every agent, branch, resource and checkpoint in the registry (`state.md`).
4. Read every checkpoint and report against the terminal states below (`evaluating-reports.md`); reply the same turn.
5. Relay across streams: move a working design to the stream that needs it, broadcast decisions and corrections to every affected agent at once, and give each shared interface (a layout, flag, API) one owner. Move compute from streams that finished or parked to those that need it, and release what nothing needs (`resources.md`).
6. Verify, integrate, report.

## Terminal states

Agents tend to stop before the work is done, most often when an improvement is known to be possible in principle (a fusion the baseline already has, a copy, conversion, round trip or sync that need not exist, a rate below a measured bound) and the first design hits a barrier. Your job is to push every stream to one of these, and only these:

- **Done**: the acceptance check named in the brief passes, run or recomputed by someone other than the stream agent.
- **Proven blocker**: a fundamental limit, measured with numbers, after at least two genuinely different designs were built and measured, confirmed by one independent audit (a fresh agent given the code and data, not the conclusion). Final after that audit; don't audit the same barrier twice.
- **Not worth it**: a measured ceiling on the remaining gain (never an estimate) falls below the threshold the brief sets. For a speculative idea, one solid measured design is enough to establish the ceiling.
- **Escalated**: a decision or resource only the user can provide, with the exact question asked. The stream parks; the others continue.
- **Out of time**: valid only once the hard stop has passed or less than one checkpoint interval remains. Records the best measured state, the next concrete step and its expected gain as open work, never as "blocked".

Not terminal, however it is phrased: "slower so far", "the first design runs out of registers or memory", "the library can't do that", "needs the other stream first", "out of time" with time left, or simply stopping. On any of these, reply the same turn with concrete design candidates (from other streams, the literature, an audit), the target and the next checkpoint; resume an agent that stopped early; resolve a cross-stream dependency by assigning it an owner. If an agent stalls twice on the same barrier, launch the independent audit or a competing design (a second agent, possibly with a different approach or language) within budget, rather than accepting the stall.

A round ends when every stream is terminal or the hard stop is reached. After that, start no new agents without the user, and summarize each stream: state, evidence, open work.

## Non-negotiables

- **The bar is set in the brief**: acceptance check, known overheads to eliminate, prior work searched first (including teammates' branches and open PRs), the two-designs rule, the not-worth-it threshold, budget and hard stop.
- **Never relay a give-up unexamined.** Split every negative result into fundamental and implementation parts; send the implementation parts back with a concrete follow-up and the number you expect.
- **Nothing reaches the user unverified.** Checkers are fresh agents given the claims and file pointers, not your conclusions; they answer OK or WRONG with evidence, re-deriving numbers from raw outputs rather than a stream's summary. Every number names its baseline and the run it came from; say what a measurement cannot show; correct your own relayed errors explicitly.
- **Grant only the authority the user gave.** Renewed resources, PRs and extra resources trace to a user decision recorded verbatim (`state.md`); each push needs its own explicit approval, and an earlier one never carries over; otherwise the stream is escalated. An action a permission check refused is never retried through another agent, a reworded command or another tool; surface it to the user.
- **Git**: one writer per branch; integration takes only commits a stream reported; no commits, stashes or rebases in another agent's worktree or branch; every shared benchmark runs a named commit, not a live worktree. Worktrees via `git tree branch` per the global worktree rule; each worktree keeps one draft PR.md (pr-description skill), owned by its writer.

## Performance work

- The acceptance check measures the production path against a pinned baseline (a commit plus config, on the same nodes and in the same session as the change). Headline that, not an intermediate branch or an isolated microbenchmark; use microbenchmarks for per-op detail.
- Each stream traces the production path before optimizing (profiling skill), including host syncs, and publishes the per-kernel breakdown; later claims are judged against it.
- A fundamental limit means measured against a roofline, an Amdahl bound or a hardware rate.
- Freeze timing arms: `git archive <sha>` into a directory when the arm runs on the shared interpreter or virtual environment, a detached worktree when it needs its own build or environment. Agents tuning one code path can share one worktree with disjoint file ownership and the orchestrator committing; independent directions get a worktree each.
- For running profiling and tuning agents (allocations, a dedicated timing agent, what to ask of them): profiling skill, `tools/agents.md`.

## Talking to the user

Lead with the result against the baseline that matters. Keep running updates to a line or two. Ask explicitly for decisions that are the user's (pushes, scope, adopting anything that changes behavior or numerics) and record the answers.
