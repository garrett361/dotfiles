---
name: commit-staged
description: Commit staged changes with a clean conventional commit message. Use when the user wants to commit staged work, write a commit message, or says "commit staged", "commit this", or "/commit-staged".
allowed-tools: Bash(git:*)
---

# Commit Staged Changes

Commit whatever is currently staged in git with a well-crafted conventional commit message.

This skill runs non-interactively (typically via `claude -p`). Never ask questions, request confirmation, or wait for user input. Analyze the diff, write the message, commit, and report the result.

## Steps

1. **Gather context**

   Run in parallel:
   - `git diff --cached` — the full staged diff
   - `git log --oneline -10` — recent commits for style consistency

   If the user provided additional text alongside the command (e.g., `/commit-staged made CLAUDE.md shorter`), treat it as intent context — it should inform the commit message, taking priority over what you'd infer from the diff alone.

   If the diff is empty, tell the user nothing is staged and stop.

   If the diff is very large (hundreds of files or truncated output), fall back to `git diff --cached --stat` and `git diff --cached --name-only` to infer intent. For binary-only changes, rely on filenames and stat output.

2. **Write the commit message**

   **Format**: `type(scope): concise description`

   Types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `build`, `ci`, `perf`

   Scope is optional but preferred when changes target a clear area. Omit if changes span many areas.

   **Guidelines**:
   - Lead with what changed and why, not how
   - Imperative mood ("add", "fix", "update")
   - Most commits need only the subject line. A body is the exception, not the norm — add one only when the subject alone would leave a reader genuinely confused about *why* the change was made. When included, keep it as short as possible.
   - If multiple logical changes are staged, summarize the primary intent
   - Match tone and style of recent commits in the repo


   **IMPORTANT**: Keep the first line under 72 characters


   **Examples**:
   ```
   feat(model): add multi-head attention with rotary embeddings
   ```
   ```
   fix(api): handle null response from upstream auth service

   The /token endpoint occasionally returns null when the OAuth
   provider is rate-limiting. Previously this caused an unhandled
   TypeError in the session middleware.
   ```

3. **Commit**

   ```bash
   git commit -m "$(cat <<'EOF'
   <message here>
   EOF
   )"
   ```

4. **Confirm** — run `git log -1 --oneline` and show the result.

## Rules

- **No co-author line.** Do not add `Co-Authored-By` or any attribution to Claude/AI. You are a tool for writing the message, not a contributor.
- **No self-reference.** Do not mention AI, Claude, or automation in the commit message.
- **Do not stage additional files.** Only commit what is already staged.
- **Do not push.** Only commit locally.
- **No questions.** Do not ask for confirmation or clarification. Make your best judgment and commit.
