---
name: plan-md
description: Create a staged PLAN.md for complex multi-session work. Breaks tasks into numbered stages with tests, verification, and session continuity.
---

# /plan-md

Create a structured PLAN.md that breaks complex work into numbered stages for multi-session execution.

**Core workflow**: After each stage, the Claude Code context is completely cleared. PLAN.md is the *only* thing that carries over between sessions. It must contain everything a fresh session needs to understand the current state and continue work.

## EXECUTE THESE STEPS NOW

When this skill is invoked, you MUST execute these steps immediately.

### Step 1: Parse Task Description

Extract the high-level task description from `$ARGUMENTS`.

If `$ARGUMENTS` is empty, use AskUserQuestion to ask: "What task should I plan? Describe the feature, refactor, or work to break into stages."

### Step 2: Enter Plan Mode

Use EnterPlanMode to begin exploration. In plan mode:

1. **Read project context** - Check CLAUDE.md, README.md, and any relevant docs
2. **Explore the codebase** - Understand architecture, patterns, existing code related to the task
3. **Identify scope** - What files exist, what needs to be created/modified, what tests exist
4. **Map dependencies** - Which pieces must be built before others

Spend sufficient time exploring. The quality of the plan depends on understanding the codebase.

### Step 3: Design Stages

Break the work into **3-7 stages** following these principles:

- **Each stage is independently verifiable** - has its own tests and Definition of Done
- **Stages build on each other** - later stages depend on earlier ones
- **Each stage fits in one session** - not too large, not trivially small
- **First stage establishes foundations** - core types, interfaces, base structure
- **Last stage integrates and polishes** - end-to-end tests, docs, cleanup

For each stage, determine:
- Files to create or modify
- What to implement (specification)
- Tests to write for verification
- Definition of Done checklist (3-5 checkboxes)

### Step 4: Write PLAN.md

Write `./PLAN.md` in the project root (or working directory) using this template:

```markdown
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
5. Begin work on the next stage

### Completing a Stage (CRITICAL)

After finishing a stage, the context will be completely cleared. PLAN.md is the
sole bridge to the next session. You MUST update it thoroughly before stopping.

1. Verify all Definition of Done checkboxes are checked
2. Run the verification commands listed for that stage
3. **Update the completed stage** — add these sections under the stage heading:
   - **What Was Built**: Concrete summary of what was implemented (files, classes, functions)
   - **Key Implementation Details**: Decisions made, patterns used, gotchas, anything a fresh session needs to know to avoid re-discovering or contradicting
   - **Verification**: Paste actual test output / command results confirming completion
4. **Review the entire PLAN.md top-to-bottom** and update anything that is now stale:
   - Check remaining stages: do their specs, file lists, or assumptions still hold given what was actually built? Revise if needed.
   - Update the Context section if architecture decisions evolved
   - Update the File Structure tree to reflect reality
   - Update Critical Files if new important files were created
5. Update the Progress Tracker table
6. Add a row to the Session Log

The goal: a fresh Claude Code session that reads only this file should be able to
pick up exactly where you left off with zero ambiguity.

### After Completing a Stage — STOP

After updating PLAN.md, **stop and present a summary to the user**. Do NOT
start the next stage. The user will:

1. **Review** the changes (e.g., `git diff`, read modified files, run tests)
2. **Commit** — either manually or by asking Claude to commit (e.g., `/commit`)
3. **Clear context** (`/clear` or start a new session)
4. **Continue** by saying "Read @PLAN.md and complete the next stage."

Each stage runs in its own fresh Claude Code session. Committing after each
stage keeps the git history clean and makes it easy to revert a single stage
if needed.

### Rules
- Complete stages in order — do not skip ahead
- Each stage must pass its own tests before moving on
- **One stage per session** — after completing a stage, STOP. Update PLAN.md, then wait for the user to review changes and give the go-ahead before proceeding. Do NOT automatically start the next stage.
- **Commit after each stage** — the user will review and commit (or ask you to commit) after each stage. This keeps git history clean with one commit per stage.
- **Reset context between stages** — after reviewing and committing, the user will clear context (`/clear` or new session) before starting the next stage. This ensures each stage starts fresh with only PLAN.md as context.
- **PLAN.md is the single source of truth** — after each stage, review and update the *entire* document, not just the completed stage
- When updating, ask: "If I lost all context and only had this file, could I continue?" If not, add what's missing

## Progress Tracker

| Stage | Name | Status | Session |
|-------|------|--------|---------|
| 1 | <name> | Not Started | - |
| 2 | <name> | Not Started | - |
| ... | ... | ... | ... |

## Context

### Goal
<1-2 sentence description of what we're building and why>

### Architecture Decisions
<Key design choices, patterns, constraints discovered during exploration>

### Key Constraints
<Technical limitations, compatibility requirements, invariants to respect>

---

## Stage 1: <Name>

**Files to create/modify:**
- `path/to/file.py` - <what and why>

**Specification:**
<What to implement in this stage. Be specific enough that a fresh session with zero prior context can execute without ambiguity. Include concrete details: function signatures, class names, expected behavior, edge cases.>

**Tests:**
- <Test description and what it verifies>

**Definition of Done:**
- [ ] <Concrete, verifiable criterion>
- [ ] <Concrete, verifiable criterion>
- [ ] All tests pass
- [ ] Lint passes

---

## Stage 2: <Name>
<Same structure as Stage 1>

---

<Repeat for each stage>

---

## File Structure

<ASCII tree showing the target file layout after all stages complete>

## Verification Commands

```bash
# <Command descriptions>
<actual commands to run>
```

## Critical Files

| File | Purpose | Read-only? |
|------|---------|------------|
| <path> | <why it matters> | <yes/no> |

## Session Log

| Date | Stage | What Was Done | Notes |
|------|-------|---------------|-------|
| <date> | 0 | Created PLAN.md | Initial planning |
```

Adapt the template to the specific task — add or remove sections as appropriate. The template is a guide, not a rigid format. Smaller tasks may need fewer sections; larger tasks may need additional context sections.

**Code style in generated code**: When stage specifications include example code or when implementing stages, follow the user's global CLAUDE.md preferences. In particular: never use decorative section-separator comment headers (`# ====`, `# ----`, `# ***`, etc.) in generated code — class names, function names, and variable names should be self-documenting.

### Step 5: Exit Plan Mode

Use ExitPlanMode so the user can review and approve the PLAN.md.

After approval, tell the user:

> PLAN.md is ready. The workflow from here:
> 1. Clear context (`/clear` or start a new session)
> 2. Say: "Read @PLAN.md and complete the next stage."
> 3. After the stage is done, I will update PLAN.md and then **stop and wait for your review**
> 4. Review the changes (e.g., `git diff`, read modified files, run tests yourself)
> 5. Commit the stage (manually or ask me to `/commit`)
> 6. Clear context (`/clear` or new session) and repeat from step 2
>
> **Important**: Each stage runs in a fresh context. I will NOT continue to the next stage automatically — you always get a review + commit checkpoint between stages.

---

## When to Use

- Complex features spanning multiple files and sessions
- Large refactors that benefit from incremental progress
- Any work where losing context between sessions is costly
- Projects where you want a written record of decisions and progress

## When NOT to Use

- Simple, single-session tasks
- Quick bug fixes or small changes
- Tasks where the full scope is already clear and fits in one session
