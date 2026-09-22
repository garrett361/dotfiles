---
name: cut
description: Go back over comments, docstrings, or prose just written and cut them to the minimum that earns its place. Use when the user says the comments are too verbose, or says "/cut", "cut the comments", "fewer comments", "that's too wordy" about code or docs just produced. Not for cutting features, code, or scope.
---

# Cut

You wrote too much. Go back over what you just wrote and cut it.

## The standard

A comment is a last resort, not a courtesy. A precise name removes the need for
most of them, and the reason a change was made belongs in the commit message,
where it is read once, rather than beside the code, where it is read forever and
rots. What survives is the one fact a careful reader could not recover from the
code in front of them, on one line. Everything else goes, and deleting is the
default outcome rather than shortening.

## Steps

1. Take the target from whatever the user typed after `/cut` first: a path, a
   commit range, a file, or a specific complaint. With nothing given, work out
   what they mean by what you just did, in this order: files edited this
   session, then the uncommitted diff (`git diff HEAD` and untracked files),
   then commits you made that the user has not reviewed yet. Say which target
   you picked in one line before editing.
2. Read every comment and docstring your work added or touched inside that
   target. Comments that predate your work are not yours to cut.
3. For each one, apply the first option that fits: delete it; or, if it carries
   one genuinely non-obvious fact, keep that fact on one line; or, if it exists
   only because a name is vague, rename the variable or function and delete the
   comment.
4. Cut the clear violations without asking. Ask only where the call is genuinely
   ambiguous: the surrounding file comments this kind of thing at this length,
   or a docstring convention may require more than one sentence. Ask all such
   questions in one batch, not one at a time.
5. Report as a plain list of `path:line` plus a few words on what went. If the
   target was already committed, leave the edits unstaged and ask whether to
   amend, fixup, or commit separately. Never rewrite a commit on your own.

## Cut on sight

- Anything that restates what the code plainly does.
- History and rationale: what it used to do, what broke, why the approach
  changed. That belongs in the commit message.
- Line numbers in other files, and any mention of a flag or construct not
  present in the code.
- Two or more lines where one carries the fact.
- Decorative headers.
- Docstrings past one sentence, unless the repo's convention requires more.
- `TODO`, `FIXME`, and commented-out code added without asking.

## Prose

When the target is markdown or docs rather than code, the job is the same. Cut
hedges, flourishes, metaphors, restatements of a point already made, and any
closing paragraph that summarizes what was just said. Keep the claim and the
reasoning that supports it. Remove em-dashes; they belong in no file.

## Rules

- **Deletion is the default.** Reach for a shorter comment only when a fact
  would otherwise be lost.
- **Only your own additions.** The user edits these files at the same time, so
  re-check the diff before touching a line and leave everything you did not
  write alone.
- **Nothing else changes.** No reformatting, no refactoring, no unrelated fixes
  while in here.
- **Do not compensate.** Cut text does not get relocated into the commit
  message, the reply, or a longer variable name, unless it is genuine change
  rationale that belongs in a commit body.
- **Keep the report short.** A list of what went, not a defense of each
  decision.
