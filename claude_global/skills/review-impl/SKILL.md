---
name: review-impl
description: Fan out reviewer subagents on the changes implementing the current plan, triage critical issues, and revise. Use after implementing a plan when the user wants to review the implementation with subagents, or says "review impl", "review the implementation", "/review-impl".
---

# Review Implementation

Review the changes implementing the plan in context with independent reviewer
subagents, then revise. Consult the user only on borderline calls.

Default to one reviewer subagent covering all lenses, and one round. Split the
lenses or take a specific focus only when the invocation asks for it, or when the
diff is large enough that one reviewer cannot give each lens real attention.
Further rounds happen only when the invocation asks for them (step 5).

## Steps

1. Identify the changes implementing the plan in context: both committed and
   uncommitted work, keeping only what the plan owns and ignoring unrelated
   diffs (staged vs unstaged is not the axis). If no plan is in context or
   nothing is plan-relevant, say so and stop.
2. Launch one reviewer subagent covering bugs, faithfulness and completeness to
   the plan, and convention (per `CLAUDE.md` / `AGENTS.md` and local style)
   together. Split those into 2-3 parallel reviewers with distinct lenses only
   under the escalation conditions above. Inline the plan text and the scoped
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
