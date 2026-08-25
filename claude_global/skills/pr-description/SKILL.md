---
name: pr-description
description: Draft a PR description (short prose intro, bullets only if needed) from conversation context, git-tree parent branch, or branch diff, iterate with the user, then save the agreed text to a local markdown file. Use when asked to write/draft/update a PR description, or "/pr-description".
---

# PR Description

## 1. Gather context

Prefer sources in this order, stopping as soon as one gives enough to draft
from:

1. This conversation's own knowledge of what was just implemented, if the
   change being described was done earlier in this session.
2. Any commentary the user typed after `/pr-description`.
3. If this is a `git tree` stacked branch, run `git tree --json` and look up
   the current branch (`git branch --show-current`) in its `branches` array.
   If found, use that entry's `parent` field as the base instead of the
   repo's default branch: `git diff <parent>...HEAD`, `git log
   <parent>..HEAD`.
4. Otherwise diff/log against the repo's default branch: `git diff
   <base>...HEAD`, `git log <base>..HEAD`.
5. Only ask the user (via `AskUserQuestion`) if the scope or base is still
   unclear after the above.

State which source you used (e.g. "using this session's changes" / "diffing
against parent branch `foo`" / "diffing against `main`") so the user can
correct it early if it's wrong.

## 2. Draft

A paragraph on the goal, motivation, and what changed and why. A single
sentence is the ideal to strive for whenever it can carry the point on its
own; expand to a few sentences only as far as genuinely needed. Then a plain
bullet list, only if there are necessary PR details the prose didn't cover.
Never use section headers like `## Summary` for this part.

Exception: add a `## Verification` section, but only when there's a
non-trivial verification step a reviewer wouldn't otherwise know to run,
e.g. a specific `uv run ...` command, a script, or a manual repro. Don't add
this section by default.

## 3. Iterate

Show the draft in chat and revise based on feedback. Do not write anything
to disk until the user explicitly agrees on the text.

## 4. Write the file

Find the repo root with `git rev-parse --show-toplevel`. If `PR.md` already
exists there, ask the user (via `AskUserQuestion`) what filename to use
instead rather than guessing or overwriting. Write the agreed text as
GitHub-flavored markdown, then report the path written.
