---
name: plan-md
description: Create a staged PLAN.md for complex multi-session work. Breaks tasks into numbered stages with verification, tracking, and session continuity.
---

# /plan-md

Create a structured PLAN.md that breaks complex work into numbered stages for multi-session execution.

**Core workflow**: After each stage, the Claude Code context is typically cleared. PLAN.md is the *only* thing that carries over between sessions. It must contain everything a fresh session needs to understand the current state and continue work.

**The plan file lives in the project root** (default: `./PLAN.md`, but the user may choose a different name in Step 1). It is committed to git alongside the code and updated with each stage, so the plan's evolution is tracked in version history. Never write it to `~/.claude/plans/` or any other location — always relative to the repo root.

**Security**: PLAN.md is committed to git — treat it as public. No secrets, no absolute paths, no sensitive details. Reference environment variables by name (e.g., `$OPENENV_URL`) instead of their values.

## EXECUTE THESE STEPS NOW

When this skill is invoked, you MUST execute these steps immediately.

### Step 1: Parse Task Description

Extract the high-level task description from `$ARGUMENTS`.

If `$ARGUMENTS` is empty, use AskUserQuestion to ask: "What task should I plan? Describe the feature, refactor, or work to break into stages."

Use AskUserQuestion to confirm the plan file name: "The plan will be written to `./PLAN.md`. Is that fine, or should it use a different name/path?" Provide `PLAN.md (Recommended)` as the first option and `Custom name/path` as the second.

### Step 2: Enter Plan Mode

Use EnterPlanMode to begin exploration. In plan mode:

1. **Read project context** - Check CLAUDE.md, README.md, and any relevant docs
2. **Explore the codebase** - Understand architecture, patterns, existing code related to the task
3. **Identify scope** - What files exist, what needs to be created/modified, what verification infrastructure exists
4. **Map dependencies** - Which pieces must be built before others
5. **Assess uncertainty** - Are there unknowns that need a spike/prototype before committing to a full plan?

Spend sufficient time exploring. The quality of the plan depends on understanding the codebase.

### Step 3: Design Stages

Break the work into stages — as many as the work naturally requires. Each stage should be completable in one session and independently verifiable. Don't artificially inflate or compress the number of stages.

**Progressive refinement**: Fully specify the first 2-3 stages. Later stages can be "sketch" stages with just a goal, rough scope, and key questions to resolve. Each stage completion includes refining the next stage's specification based on what was learned.

**When to include a spike stage**: If the task involves unfamiliar code, an external API, or significant architectural uncertainty, make stage 1 a time-boxed spike that validates the core approach before committing to the full plan. A spike stage's Definition of Done is a go/no-go decision, not working code.

### Step 4: Draft the Plan

Design the full plan content during plan mode using the template below. **Start minimal and add sections only as needed.** The required sections are: Goal, Progress Tracker, Stages, and Session Log. Everything else (Architecture Decisions, File Structure, Critical Files, Verification Commands) is opt-in based on project complexity.

````markdown
# Plan: <Title>

**Status**: In Progress
**Created**: <YYYY-MM-DD>
**Branch**: <current git branch>

## How to Use This Document

### Starting a New Session
1. Read this entire PLAN.md first
2. Check the Progress Tracker to find the next incomplete stage
3. Read that stage's specification and Definition of Done
4. If prior stages are complete, read their "What Was Built" sections for context
5. If the next stage is a sketch, refine it into a full specification before starting work
6. Begin work on the next stage

### Completing a Stage (CRITICAL)

After finishing a stage, PLAN.md is the sole bridge to the next session.
You MUST update it before stopping.

1. Run the verification steps listed for that stage
2. **Check off every Definition of Done checkbox** — edit each `- [ ]` to `- [x]` as you confirm it. If a criterion changed during implementation, update the text to reflect what actually happened.
3. **Update the completed stage** — add these sections under the stage heading:
   - **What Was Built**: Concrete summary of what was implemented (files, classes, functions)
   - **Key Implementation Details**: Decisions made, patterns used, gotchas — anything a fresh session needs to know
   - **Verification**: Paste actual test output / command results confirming completion
4. **Update what changed elsewhere** — refine the next stage's spec (especially if it's a sketch), update Context if architecture decisions evolved, and fix any other stale sections. Do NOT rewrite sections that haven't changed.
5. Update the Progress Tracker table
6. **Add a row to the Session Log** — every completed stage MUST have a Session Log entry. No exceptions.

The goal: a fresh Claude Code session that reads only this file should be able to
pick up exactly where you left off with zero ambiguity.

### After Completing a Stage — STOP

After updating PLAN.md, **stop and present a summary to the user**. Do NOT
start the next stage unless the user explicitly says to continue. The default
workflow is:

1. **Review** the changes (e.g., `git diff`, read modified files, run verification)
2. **Commit** — either manually or by asking Claude to commit (e.g., `/commit`)
3. **Clear context** (`/clear` or start a new session)
4. **Continue** by saying "Read @PLAN.md and complete the next stage."

If the user says "continue to the next stage" without clearing context, proceed —
but still update PLAN.md fully before starting the next stage, since context may
be cleared at any time.

### Revising the Plan

Plans rarely survive first contact with implementation. When things change:

- **Stage too large?** Split it. Renumber subsequent stages and document the split in the Session Log.
- **Approach invalidated?** Update Context with what was learned. Revise affected stages. Mark abandoned stages as "Skipped" in the Progress Tracker.
- **New requirement discovered?** Add new stages or expand existing ones.
- **Mid-stage failure?** Do NOT mark the stage as complete. Document what worked and what failed in a "Partial Progress" section under the stage.

When revising, always update the Session Log with what changed and why.

## Progress Tracker

| Stage | Name | Status | Date |
|-------|------|--------|------|
| 1 | <name> | Not Started | - |
| 2 | <name> | Not Started | - |
| ... | ... | ... | ... |

Status values: Not Started, In Progress, Complete, Skipped

## Context

### Goal
<1-2 sentence description of what we're building and why>

---

## Stage 1: <Name>

**Files to create/modify:**
- `path/to/file.py` - <what and why>

**Specification:**
<What to implement. Be specific enough that a fresh session with zero prior context can execute without ambiguity. Include concrete details: function signatures, class names, expected behavior, edge cases.>

**Verification:**
- <What to verify and how — tests, commands, manual checks, linter, etc.>

**Definition of Done:**
- [ ] <Concrete, verifiable criterion>
- [ ] <Concrete, verifiable criterion>
- [ ] All verification steps pass

---

## Stage 2: <Name>
<Same structure as Stage 1 if fully specified>

---

## Stage N: <Name> (sketch)

**Goal:** <What this stage accomplishes>

**Rough scope:** <Approximate files and areas of the codebase involved>

**Open questions:**
- <What must be resolved by earlier stages before this can be fully specified?>

---

## Session Log

| Date | Stage | What Was Done | Notes |
|------|-------|---------------|-------|
| <date> | 0 | Created PLAN.md | Initial planning |
````

Add these optional sections when useful:
- **Architecture Decisions / Key Constraints** under Context — for non-trivial design choices
- **File Structure** — ASCII tree of the target layout after all stages
- **Critical Files** — table of files that matter, with purpose and read-only status
- **Verification Commands** — global commands that apply across stages

**Git workflow**: Work on a feature branch. Each stage = one commit on that branch.

**Code style in generated code**: Follow the user's global CLAUDE.md preferences. Never use decorative section-separator comment headers (`# ====`, `# ----`, `# ***`, etc.).

### Step 5: Exit Plan Mode and Write the Plan File

Use ExitPlanMode so the user can review and approve the plan. After approval, write the plan to the chosen file path (default `./PLAN.md`) in the project root.

Then tell the user:

> The plan is ready. The workflow from here:
> 1. Clear context (`/clear` or start a new session)
> 2. Say: "Read @<plan-file> and complete the next stage."
> 3. After the stage is done, I will update the plan and then **stop and wait for your review**
> 4. Review the changes, commit the stage, clear context, and repeat
>
> **Tip**: If two stages are tightly coupled, you can say "continue to the next stage" to skip the context clear.

(Replace `<plan-file>` with the actual file name chosen in Step 1.)
