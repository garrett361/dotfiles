---
name: cut
description: Go back over comments, docstrings, or prose just written and cut them to the minimum that earns its place. Use when the user says the comments are too verbose, too wordy, or asks for fewer comments on code or docs just produced. Not for cutting features, code, or scope.
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

## Workflow

1. Take the target from whatever the user typed with the invocation: a path, a
   commit range, a file, or a specific complaint. With nothing given, use the
   files you edited this session, then the uncommitted diff, then commits you
   made that the user has not reviewed. Name the target in one line first.
2. Read every comment and docstring your own work added or touched there.
   Comments that predate your work are not yours to cut.
3. For each, take the first option that fits: delete it; keep one genuinely
   non-obvious fact on one line; or rename the vague thing it explains and
   delete it.
4. Cut clear violations without asking, and batch any genuinely ambiguous calls
   into a single question.
5. Report a plain list of `path:line` and a few words on what went. Leave edits
   to already-committed work unstaged and ask how to land them.

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

## Rules

- Deletion is the default. Shorten only when a fact would otherwise be lost.
- Touch only your own additions, re-checking the diff before each edit.
- No reformatting, refactoring, or unrelated fixes while in here.
- Do not relocate cut text into the reply, a commit message, or a longer name.
- In markdown and docs the job is the same: cut hedges, flourishes, and closing
  paragraphs that restate the point, and remove em-dashes.
