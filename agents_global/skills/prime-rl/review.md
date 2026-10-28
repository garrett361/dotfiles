# Reviewing a prime-rl PR

Two phases: first an independent review, then the user's own comments and questions on the PR, which may
arrive while the review is still running or after it. Keep the review independent: finish and report it
before weighing in on the user's points, and do not fold their views into it.

## Gather

- **Independent of where the review is invoked:** the current worktree may be the PR branch, a main
  checkout, or an unrelated branch. Never read the PR's code, `AGENTS.md`, or `uv.lock` from the working
  tree, and never use local `main` or `HEAD`. Instead:
  - Identify the PR by number or URL. If the user gave neither, `gh pr view --json number,url` on the
    current branch, and confirm with the user if that returns nothing or an unexpected PR.
  - Fetch into any clone of the repo (`git fetch origin pull/N/head main`; it only adds refs), record the
    head SHA, and compute the base as `git merge-base FETCH_HEAD origin/main` after that fetch.
  - Snapshot the head into the scratchpad: `git archive <head> | tar -x -C <scratch>/prN/head`. All reading,
    including `AGENTS.md`, `uv.lock` and configs, happens there. `git show <sha>:<path>` works for other commits.
  - The only exception is when the user says uncommitted local changes are part of the review; then the
    working tree is the source, and say so in the report.
- **PR description before the diff:** `gh pr view N --json number,title,body,url,author,headRefOid`. It often
  holds the only evidence (measurements, logs, the failing run), and its claims are review targets too.
- **Scope:** `git diff <base> <head>`, or `gh pr diff N` when it matches. Ignore submodule pointer noise
  (`deps/*`) unless the PR is about them.
- **Pinned versions:** read dependency versions from the snapshot's `uv.lock`, not the local `.venv`, which
  belongs to whatever worktree the review was invoked from. When the PR leans on library behavior, ask for or
  locate a local checkout of that exact tag (e.g. torch at `v2.13.0`) and check it is clean at the tag.

## Review

- Fan out reviewers in parallel, read-only, each with the diff and PR body inlined. Lenses, merged for a
  small diff:
  - **Correctness:** what the change does on every path it touches (offload and non-offload, SFT and RL,
    fresh start and resume).
  - **Claims:** every factual statement in new comments and the PR description, verified against the pinned
    library source with `file:line`. Verdict per claim: true, false, or partial.
  - **Evidence:** does the reported data establish causality, and which measurement would settle what it
    does not (e.g. peak allocated next to peak reserved).
  - **Conventions:** AGENTS.md and the user's CLAUDE.md.
- When a claim is about library failure modes, have a subagent search upstream issues and note the fix
  version relative to the pinned one.
- Separate measured, code-verified, and inferred in every finding.

## Report

- Lead with the verdict, then critical and borderline findings, each with a recommendation.
- Supporting links are permalinks: prime-rl at the PR head SHA, libraries at the pinned tag. Say which links
  were not opened on GitHub.
- Write the review to `~/tmp/review-prime-rl-<pr#>.md` by default (create `~/tmp/` if missing) and iterate on
  that file with the user; it is pasted into GitHub as the review body. Never post to GitHub without explicit
  approval.
- Start the file with this skeleton. Leave the preamble for the user, who writes their own summary there;
  everything Claude writes goes below the rule:

  ```
  <user's preamble>

  Generated below, for your agent:

  ---

  <review body>
  ```

- Answer the user's comments and questions in conversation, and fold agreed wording into the file.
- Write the review body for whoever acts on it, often another agent rather than the PR author: just enough to
  be actionable, no more.
  - Describe only the code at head. Do not cite commit messages, earlier revisions, or where a claim was first
    written; link the current line that makes or contradicts it.
  - Corrections and bugs: a GitHub permalink at the PR head SHA with line numbers
    (`.../blob/<sha>/<path>#L<a>-L<b>`) for every location, the defect in one or two sentences, and the
    expected behavior. Permalinks render in the GitHub UI and are precise enough for an agent to act on.
    GitHub expands a raw prime-rl permalink into a code snippet, so put it at the end of a sentence, never
    inside parentheses or markdown link syntax.
  - Design changes: the design goal, the main shortcomings of the current code (with permalinks), and
    pseudocode of the proposed shape. Do not write a full implementation.

## Walkthrough and pending inline comments

Once the review file is written and the user's comments are answered, go through the findings with the user one
item at a time, with a recommendation. For each, the user decides: edit it, keep it in the top-level review, move or
copy it into an inline code comment, or drop it.

- **Short top-level items:** often one sentence, with a hyperlink to the exact upstream line that proves the claim,
  so an agent can verify it in one click. The inline comment carries the detail.
- **Links into other repos:** markdown hyperlinks at a commit SHA, not a branch or tag. prime-rl links stay raw
  permalinks at the PR head SHA so GitHub renders them. Before citing a line in a repo not cloned locally, fetch it
  at that SHA (`gh api 'repos/<o>/<r>/contents/<path>?ref=<sha>' -q .content | base64 -d`) and check the numbers.
- **Inline comments go into one pending review, which the user submits:**
  - GitHub allows one pending review per user per PR; check for one first (`gh api repos/<o>/<r>/pulls/N/reviews`,
    state `PENDING`).
  - Create it with `gh api -X POST repos/<o>/<r>/pulls/N/reviews --input <json>`: `commit_id` = head SHA, a
    `comments` array (`path`, `line`, `side: RIGHT`, plus `start_line`/`start_side` for ranges), and no `event`,
    so it stays pending.
  - Add later comments with the GraphQL `addPullRequestReviewThread` mutation (`pullRequestReviewId` = the review's
    `node_id`). The REST `pulls/N/comments` endpoint publishes immediately, so never use it here.
  - Never submit the review; the user submits it from the GitHub UI.
  - Keep each inline comment to one or two sentences, about as long as the matching bullet in the review file.
    Go longer only when pseudocode or a suggested replacement is needed to explain the change.
  - A comment's line must fall inside a diff hunk. When the code at fault is unchanged (outside the diff), anchor
    the comment on the changed line that calls it.
  - The user marks items to inline in the review file (e.g. a trailing `GG: inline`). After posting, replace each
    mark with a status tag such as `[posted inline on L130, pending review]`, and keep the item's number unchanged
    so earlier references to it still hold. The tags show which items are covered by the pending review.
- **Side questions** raised during the walkthrough ("is this patch needed?", "did someone already do this?") go to
  subagents; fold the answers into the relevant item rather than adding sections.

## Follow-up review: tracking the user's earlier comments

When the user has already reviewed the PR and wants to know what became of that feedback, this is a third
deliverable next to the independent review, not a replacement for it.

- **Gather every comment with its anchor:** `gh api repos/{owner}/{repo}/pulls/N/reviews` (review bodies,
  which often hold the design-level feedback), `.../pulls/N/comments` (inline threads; group by
  `in_reply_to_id`), and `.../issues/N/comments`, all with `--paginate`. Record each comment's
  `original_commit_id` and the review summary's requests (e.g. "verify this e2e"). Include bot findings
  the user replied to or that touch the same code. Split a design-level review body into its separate
  asks (each proposal, question, and suggested test) and track each one.
- **Check whether the author replied at all:** list `user.login` across every thread. When there are no
  replies, every "why?" was answered only by code or the PR description, if at all.
- **Diff from the anchor, not from main:** `gh api repos/{owner}/{repo}/compare/<anchor>...<head>` with
  `-H "Accept: application/vnd.github.diff"`, plus the commit messages since the anchor. Merges from main
  inflate this diff; restrict it to the PR's own files.
- **Keep independence:** the independent reviewers get the head diff and PR body, not the earlier
  comments. A separate agent does the tracking.
- **Verify against head code, not commit messages.** "Address review" commits often revert rather than
  fix. Code at head can be read from a snapshot: `git fetch origin pull/N/head` in a clean checkout, then
  `git archive FETCH_HEAD | tar -x -C <scratch dir>`. To confirm a revert, diff the file between the merge
  base and head: no output means it is back to main.
- **One verdict per comment, from a fixed set:** addressed as suggested; addressed differently; mooted
  (the code was deleted); reverted (the change commented on was dropped instead of justified); partial;
  answered in thread only; not addressed. Judge the code change and the answer separately: a question
  ("why did this change?") answered only by a revert leaves the reason unstated, which matters when the
  revert itself has consequences.
- **Check each fix for what it reopens:** a revert can bring back a bot finding or remove a capability
  the PR description still claims. A request to run something (e2e, a benchmark) is addressed only if the
  PR shows a run on the post-fix head that exercises the affected path. When the PR does not name the
  commit a run used, compare the request's timestamp with the commit dates and say the run is undated.
- **Separate the user's own asks from their consequences:** when a fix the user requested (e.g. "drop this
  workaround") is what reopens a bug, say so, so the follow-up is a decision for the user, not a
  complaint about the author.
- **Report:** a table of comment (permalink), verdict, evidence at head `file:line`, follow-up, then
  drafted replies for the comments worth re-raising. Keep rows short; put long evidence in a list below.

## The user's comments

- Answer each comment or question against the code and sources, with `file:line`. Push back when the user's
  reading does not hold, and revise earlier findings when a comment exposes a mistake.
- When the user drafts a GitHub comment, check every claim in it and propose precise wording with
  supporting permalinks, and put it in the review file once agreed.
- Do not edit the PR's code unless asked; the output is review text.
