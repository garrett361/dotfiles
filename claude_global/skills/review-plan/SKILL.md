---
name: review-plan
description: Fan out reviewer subagents on a plan, triage critical issues, and revise. Use when the user wants to review or stress-test a plan with subagents before implementing, or says "review plan", "review the plan", "/review-plan".
---

# Review Plan

Stress-test the plan in context with independent reviewer subagents, then revise.
Consult the user only on borderline calls.

Default to one reviewer subagent covering all lenses, and one round. Split the
lenses or take a specific focus only when the invocation asks for it, or when the
plan is large enough that one reviewer cannot give each lens real attention.
Further rounds happen only when the invocation asks for them (step 5).

## Steps

1. Identify the plan in context (plan-mode output or a just-written plan file).
   If none, say so and stop.
2. Launch one reviewer subagent covering soundness, completeness, code/design
   smells, test coverage (if applicable), and risk. Split those into 2-3 parallel
   reviewers with distinct lenses only under the escalation conditions above.
   Inline the full plan text into each prompt (subagents do not see this
   conversation). Tell each to return only critical and borderline findings (drop
   nits) and to review only, not spawn subagents.
3. Dedupe and triage into critical / borderline / minor. Treat genuine reviewer
   disagreement as borderline.
4. Fix every critical issue in the plan. For borderline items, give the user
   your recommendation and let them decide; if non-interactive, list them in the
   report instead. Do not change the plan's intent without asking.
5. One invocation is one round, where a round is steps 2-4. If the round found
   nothing critical, report the plan clean. If it found criticals, stop once the
   fixes are in and discuss with the user before any further round. Never launch
   the next round on your own. An invocation that explicitly asks to loop until
   clean, or for a set number of rounds, overrides this.
6. Summarize what changed, and name any critical left unresolved.
