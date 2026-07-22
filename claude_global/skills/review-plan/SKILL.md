---
name: review-plan
description: Fan out reviewer subagents on a plan, triage critical issues, and revise until clean. Use when the user wants to review or stress-test a plan with subagents before implementing, or says "review plan", "review the plan", "/review-plan".
---

# Review Plan

Stress-test the plan in context with independent reviewer subagents, then revise
until clean. Consult the user only on borderline calls. Match the review depth to
the plan: a small or simple plan warrants a single quick pass, not a multi-round
fan-out.

## Steps

1. Identify the plan in context (plan-mode output or a just-written plan file).
   If none, say so and stop.
2. Launch reviewer subagents in parallel, scaled to the plan: one for a small
   plan, up to 2-3 with distinct lenses (soundness, completeness, risk) for a
   large or complex one. Inline the full plan text into each prompt
   (subagents do not see this conversation). Tell each to return only critical
   and borderline findings (drop nits) and to review only, not spawn subagents.
3. Dedupe and triage into critical / borderline / minor. Treat genuine reviewer
   disagreement as borderline.
4. Fix every critical issue in the plan. For borderline items, give the user
   your recommendation and let them decide; if non-interactive, list them in the
   report instead. Do not change the plan's intent without asking.
5. Repeat steps 2-4 until a round finds no critical issues, new or recurring.
   Cap at 3 rounds; report any still-open critical as unresolved.
6. Summarize what changed.
