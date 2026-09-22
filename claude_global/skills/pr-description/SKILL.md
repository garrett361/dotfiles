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

1-2 sentences on the goal, motivation, and what changed and why. A single
sentence is the ideal when it alone can carry the point. Then a plain bullet
list, only if there are necessary PR details the prose didn't cover. Never
use section headers like `## Summary` for this part.

Keep that list to roughly 3 bullets. Each bullet is one sentence of about
100 characters or less; add a second sentence only when it is load-bearing,
and never a third. Lead with what changed. Cut anything the prose already
said, anything the diff shows plainly, and file-by-file inventories. A
detail that needs a paragraph belongs in the code or in the PR
conversation, not here.

A results table beats prose when the claim is a measured change; it replaces
sentences rather than adding to them. Keep the whole description to one screen,
roughly 30 lines including any table.

A typical result, and the shape to aim for:

```markdown
RL compares trainer and inference logprobs token by token, so any disagreement
between the two FP8 quantizers is model-independent noise. The trainer's
activation cast is now bit-identical to vLLM's production CUDA op.

- Three kernels floor `amax` at `1e-10` and use `tl.math.div_rn` for scale and
  quotient. Triton's `/` lowers to multiply-by-reciprocal, one fp32 ULP off.
- The weight kernel is untouched: vLLM's weight path already matched at 100%.
- A new GPU test pins the equality; the trainer still imports vLLM nowhere.

| tensor | scales before | scales after |
|---|---|---|
| randn x1.0 | 41.0797% | 100.0000% |
```

Exception: add a `## Verification` section, but only when there's a
non-trivial verification step a reviewer wouldn't otherwise know to run,
e.g. a specific `uv run ...` command, a script, or a manual repro. Don't add
this section by default.

## 3. Iterate

Before showing the draft, re-read each bullet against the cap and cut it
down; a bullet that will not fit is usually two bullets or a detail worth
dropping. Show the draft in chat and revise based on feedback. Do not
write anything to disk until the user explicitly agrees on the text.

Perf numbers, scope caveats, and rejected alternatives are the usual overflow.
Offer them to the user as a follow-up PR comment rather than dropping them
silently.

## 4. Write the file

Find the repo root with `git rev-parse --show-toplevel` and write the agreed
text there as `PR.md` (GitHub-flavored markdown), since a stable default
name makes the draft easy to find and re-iterate on. If `PR.md` already exists,
ask the user (via `AskUserQuestion`) what filename to use instead rather than
guessing or overwriting. If the user named a file, use theirs instead of
the default. Report the path written.
