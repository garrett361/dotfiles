---
name: review-staged
description: Review staged git changes for code quality, bugs, and best practices. Use when the user wants to review or check staged changes before committing, or says "review staged", "/review-staged", or wants a pre-commit code check.
allowed-tools: Bash(git diff --cached*), Bash(git diff --cached --stat*), Bash(git log --oneline*), Bash(git status --short*), Read, Glob
---

# Review Staged Changes

Review whatever is currently staged in git. This runs non-interactively.
Never ask questions or wait for input. Analyze the staged diff and output a
concise code review.

## Steps

1. **Gather context**

   Run in parallel:
   - `git diff --cached` — full staged diff
   - `git log --oneline -5` — recent commits for style/context
   - `git status --short` — quick view of staged vs unstaged

   If nothing is staged, say so and stop.

   If the diff is very large (hundreds of files), fall back to
   `git diff --cached --stat` and focus on the most-changed files.

   Read any `CLAUDE.md` files found in the repo (root and subdirectories) —
   use them to inform style and convention checks.

2. **Review the changes**

   Focus on:
   - **Bugs**: Logic errors, off-by-one, null derefs, wrong conditions
   - **Security**: Hardcoded secrets/keys, injection risks
   - **Convention**: Obvious deviations from CLAUDE.md or recent commit style

   Skip:
   - Nitpicks a linter/formatter would catch (whitespace, imports, style)
   - Pre-existing issues not introduced by the diff
   - Build/test failures (assume CI handles these)
   - Missing test coverage unless CLAUDE.md explicitly requires it

3. **Output**

   Group by severity, only including non-empty categories:

   ```
   ## Critical
   - `<file>:<line>`: <issue>

   ## Warnings
   - `<file>:<line>`: <issue>

   ## Notes
   - `<file>:<line>`: <issue>
   ```

   If nothing notable: output exactly `LGTM — no issues found in staged changes.`

   One line per finding. No preamble, no closing summary.

## Rules

- No questions, no confirmation prompts. Make your best judgment.
- Read full file contents only when the diff alone is ambiguous and a few
  lines of surrounding context would clarify a real issue.
- Stay focused on the staged diff; do not review unstaged changes.
