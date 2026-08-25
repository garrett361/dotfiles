---
name: pr-description
description: Draft a PR description (short prose intro, bullets only if needed) from conversation context or a branch diff, iterate with the user, then save the agreed text to a local markdown file. Use when asked to write/draft/update a PR description.
---

# PR Description

Draft a PR description and iterate with the user before saving it anywhere.

## Workflow

1. Gather context, preferring sources in this order and stopping as soon as
   one gives enough to draft from:
   - What was implemented earlier in this session, if applicable.
   - Any commentary the user provided alongside the request.
   - If this is a `git tree` stacked branch: run `git tree --json`, find the
     current branch (`git branch --show-current`) in its `branches` array,
     and diff against that entry's `parent` field instead of the default
     branch.
   - Otherwise diff/log against the repo's default branch.
   - Ask the user only if the scope or base is still unclear after that.
2. Say which source you used so the user can correct it early if it's wrong.
3. Write a paragraph on the goal, motivation, and what changed and why. A
   single sentence is the ideal whenever it can carry the point on its own;
   expand only as far as genuinely needed.
4. Add a plain bullet list only if there are necessary PR details the prose
   didn't cover. No section headers for this part.
5. Add a `## Verification` section only when there's a non-trivial, non-
   obvious verification step a reviewer wouldn't otherwise know to run (a
   specific command, script, or repro), not by default.
6. Show the draft and revise based on feedback. Do not write to disk until
   the user explicitly agrees on the text.
7. Find the repo root (`git rev-parse --show-toplevel`). If `PR.md` already
   exists there, ask for an alternate filename instead of guessing or
   overwriting. Write the agreed text as GitHub-flavored markdown and report
   the path written.

## Rules

- Never wrap the intro/bullets in `## Summary` or any other header.
- Never write the file before the user has agreed on the text.
- Never overwrite an existing `PR.md` without asking first.
