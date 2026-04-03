---
name: commit-staged
description: Commit currently staged git changes with a clean conventional commit message. Use when the user wants to commit staged work now, says commit staged, commit this, or asks you to write and run the staged commit.
---

# Commit Staged Changes

Commit whatever is currently staged in git with a conventional commit message. Run non-interactively and commit only staged content.

## Workflow

1. Gather context in parallel:
   - `git diff --cached`
   - `git log --oneline -10`
2. If the user supplied extra context with the request, use it to guide the message.
3. If nothing is staged, say so and stop.
4. If the diff is very large or mostly binary, fall back to:
   - `git diff --cached --stat`
   - `git diff --cached --name-only`
5. Write the message in this format: `type(scope): concise description`
6. Run `git commit -m "<subject>"` unless a short body is genuinely needed.
7. If a body is needed, use a non-interactive multi-line commit message.
8. Confirm with `git log -1 --oneline`.

## Message Rules

- Valid types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `build`, `ci`, `perf`
- Scope is optional but preferred when there is one clear area
- Lead with what changed and why, not how
- Use imperative mood
- Keep the first line under 72 characters
- Match the repo's recent commit tone when practical

## Rules

- Do not stage additional files.
- Do not include unstaged changes.
- Do not push.
- Do not add AI attribution or self-reference.
- Do not ask for confirmation once the user has asked you to commit staged work.
- Do not use this skill when the user only wants message suggestions and has not asked for an actual commit.
