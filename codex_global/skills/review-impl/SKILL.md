---
name: review-impl
description: Fan out reviewer subagents on the changes implementing the current plan, triage critical issues, and revise until clean. Use after implementing a plan when the user wants to review the implementation with subagents, or says review impl, review the implementation.
---

# Review Implementation

Review the changes implementing the plan in context with independent reviewer
subagents, then revise until clean. Consult the user only on borderline calls.
Match the review depth to the diff: a small change warrants a single quick pass,
not a multi-round fan-out.

## Steps

1. Identify the changes implementing the plan in context: both committed and
   uncommitted work, keeping only what the plan owns and ignoring unrelated
   diffs (staged vs unstaged is not the axis). If no plan is in context or
   nothing is plan-relevant, say so and stop.
2. Launch reviewer subagents in parallel, scaled to the diff: one for a small
   change, up to 2-3 with distinct lenses (bugs, faithfulness and completeness
   to the plan, convention per `AGENTS.md` falling back to `CLAUDE.md`, and
   local style) for a large one. Inline the plan text and the scoped diff from
   step 1 into each prompt so all reviewers share one scope; grant file read
   access. Tell each to return only critical and borderline findings (drop
   nits) and to review only, not spawn subagents.
3. Dedupe and triage into critical / borderline / minor. Treat genuine reviewer
   disagreement as borderline.
4. Fix every critical issue in the code. For borderline items, give the user
   your recommendation and let them decide; if non-interactive, list them in the
   report instead. Stay in the plan's scope; flag unrelated issues rather than
   fixing them.
5. Repeat steps 2-4 until a round finds no critical issues, new or recurring.
   Cap at 3 rounds; report any still-open critical as unresolved.
6. Summarize what changed.
