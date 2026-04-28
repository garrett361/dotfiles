---
name: reword-commit
description: Rewrite the last commit's message with a clean conventional commit message. Use when the user wants to reword, fix, or improve the most recent commit message, or says "reword commit", "fix commit message", or "/reword-commit".
allowed-tools: Bash(git:*)
---

# Reword Last Commit

Rewrite the most recent commit's message based on what the commit actually changed. Only the message is rewritten — the working tree and index are preserved exactly as they were.

This skill runs non-interactively (typically via `claude -p`). Never ask questions, request confirmation, or wait for user input.

## Steps

1. **Gather context**

   Run in parallel:
   - `git diff HEAD~1..HEAD` — the actual diff of the last commit
   - `git log --oneline -10` — recent commits for style consistency

   If the user provided additional text alongside the command (e.g., `/reword-commit shortened the CLAUDE.md`), treat it as intent context that should inform the message, taking priority over what you'd infer from the diff alone.

   If the diff is very large or truncated, fall back to `git diff HEAD~1..HEAD --stat` and `git diff HEAD~1..HEAD --name-only`.

2. **Write the commit message**

   **Format**: `type(scope): concise description`

   Types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `build`, `ci`, `perf`

   Scope is optional but preferred when changes target a clear area. Omit if changes span many areas.

   **Guidelines**:
   - Lead with what changed and why, not how
   - Imperative mood ("add", "fix", "update")
   - First line under 72 characters
   - Most commits need only the subject line. A body is the exception, not the norm — add one only when the subject alone would leave a reader genuinely confused about *why* the change was made. When included, keep it as short as possible.
   - When a body is included, write it in GitHub Markdown: wrap file paths, CLI flags, function names, and identifiers in backticks; use bullet lists for multi-point rationale rather than dense prose.
   - If multiple logical changes are in the commit, summarize the primary intent
   - Match tone and style of recent commits in the repo

3. **Protect the index, then amend**

   `git commit --amend` will fold any currently staged changes into the amended commit, which we do not want. Before amending, check whether anything is staged:

   ```bash
   git diff --cached --quiet
   ```

   If the exit code is 1 (staged changes exist), stash them first:
   ```bash
   git stash push --staged -q
   ```

   Then amend:
   ```bash
   git commit --amend -m "$(cat <<'EOF'
   <message here>
   EOF
   )"
   ```

   If you stashed, restore immediately:
   ```bash
   git stash pop -q
   ```

4. **Confirm** — run `git log -1 --oneline` and show the result.

## Rules

- **No co-author line.** Do not add `Co-Authored-By` or any attribution to Claude/AI. You are a tool for writing the message, not a contributor.
- **No self-reference.** Do not mention AI, Claude, or automation in the commit message.
- **Message only.** Do not alter the commit's content, the index, or the working tree. The only thing that changes is the message.
- **Do not push.** Only amend locally.
- **No questions.** Do not ask for confirmation or clarification. Make your best judgment and amend.
