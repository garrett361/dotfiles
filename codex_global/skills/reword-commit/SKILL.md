---
name: reword-commit
description: Rewrite the most recent git commit message based on the last commit's actual changes. Use when the user wants to reword the last commit, fix a commit message, or says reword commit or amend the message only.
---

# Reword Last Commit

Rewrite the most recent commit message based on what the commit actually changed. Change only the message. Preserve the working tree and index.

## Workflow

1. Gather context in parallel:
   - `git diff HEAD~1..HEAD`
   - `git log --oneline -10`
2. If the user supplied extra context with the request, use it to guide the message.
3. If the diff is very large, fall back to:
   - `git diff HEAD~1..HEAD --stat`
   - `git diff HEAD~1..HEAD --name-only`
4. Write the new message in this format: `type(scope): concise description`
5. Protect the index before amending:
   - check `git diff --cached --quiet`
   - if staged changes exist, stash them with `git stash push --staged -q`
6. Amend only the message with a non-interactive `git commit --amend -m ...`
7. If staged changes were stashed, restore them immediately with `git stash pop -q`
8. Confirm with `git log -1 --oneline`

## Message Rules

- Valid types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `build`, `ci`, `perf`
- Scope is optional but preferred when there is one clear area
- Lead with what changed and why, not how
- Use imperative mood
- Keep the first line under 72 characters
- Match the repo's recent commit tone when practical

## Rules

- Do not change the commit contents.
- Do not alter unstaged work.
- Do not push.
- Do not add AI attribution or self-reference.
- Do not ask for confirmation once the user has explicitly asked to reword the last commit.
- This skill is allowed to amend because the user's request is specifically to reword the message.
