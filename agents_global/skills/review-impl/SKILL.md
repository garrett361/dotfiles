---
name: review-impl
description: Fan out reviewer subagents on the changes implementing the current plan, triage critical issues, and revise. Use after implementing a plan when the user wants to review the implementation with subagents, or says "review impl", "review the implementation", "/review-impl".
---

# Review Implementation

Review the changes implementing the plan in context with independent reviewer
subagents, then revise. Consult the user only on borderline calls.

Scale the review to the diff: one reviewer covering all lenses for a small
diff, up to 2-3 reviewers with distinct lenses for a large one, or a specific
focus when the invocation asks for it. Further rounds happen only when the
invocation asks for them (step 5).

## Steps

1. Identify the changes implementing the plan in context: both committed and
   uncommitted work, keeping only what the plan owns and ignoring unrelated
   diffs (staged vs unstaged is not the axis). If no plan is in context or
   nothing is plan-relevant, say so and stop.
2. Launch reviewer subagents in parallel, scaled as above, covering bugs,
   faithfulness and completeness to the plan, and convention (per `CLAUDE.md` /
   `AGENTS.md` and local style) between them. Inline the plan text and the scoped
   diff from step 1 into each prompt so all reviewers share one scope; grant file
   read access. Tell each to return only critical and borderline findings (drop
   nits) and to review only, not spawn subagents.
3. Dedupe and triage into critical / borderline / minor. Treat genuine reviewer
   disagreement as borderline.
4. Fix every critical issue in the code. For borderline items, give the user
   your recommendation and let them decide; if non-interactive, list them in the
   report instead. Stay in the plan's scope; flag unrelated issues rather than
   fixing them.
5. One invocation is one round, where a round is steps 2-4. If the round found
   nothing critical, report the changes clean. If it found criticals, stop once
   the fixes are in and discuss with the user before any further round. Never
   launch the next round on your own. An invocation that explicitly asks to loop
   until clean, or for a set number of rounds, overrides this.
6. Summarize what changed, and name any critical left unresolved.
