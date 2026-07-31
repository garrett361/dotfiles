---
name: review-staged
description: Review staged git changes for bugs, regressions, and convention violations before commit. Use when the user wants a pre-commit review of staged changes, says review staged, check staged changes, or asks for a staged diff review.
---

# Review Staged Changes

Review whatever is currently staged in git. Run non-interactively and make the best judgment from the staged diff.

## Workflow

1. Gather context in parallel:
   - `git diff --cached`
   - `git log --oneline -5`
   - `git status --short`
2. If nothing is staged, say so and stop.
3. If the diff is very large, fall back to:
   - `git diff --cached --stat`
   - `git diff --cached --name-only`
4. Read `AGENTS.md` files that apply to the changed files. If no `AGENTS.md` exists, also check for `CLAUDE.md` during transition.
5. Review only the staged changes.

## Focus

- Bugs: broken logic, bad conditions, incorrect assumptions, off-by-one errors
- Regressions: behavior changes that look accidental
- Security: secrets, unsafe shell usage, injection risks
- Conventions: clear violations of `AGENTS.md` or established local commit/code conventions

## Skip

- Style-only nits a formatter or linter would catch
- Pre-existing issues outside the staged diff
- Unstaged changes
- Test coverage complaints unless repo guidance makes them mandatory

## Output

- List findings first, ordered by severity.
- Use concise one-line bullets with `path:line` references when possible.
- If there are no meaningful findings, output exactly: `LGTM — no issues found in staged changes.`

## Rules

- Do not ask questions or wait for confirmation.
- Read full files only when the diff is genuinely ambiguous.
- Stay focused on the staged diff; do not review unstaged work.
