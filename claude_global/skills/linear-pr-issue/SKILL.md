---
name: linear-pr-issue
description: Create or update a Linear issue from a GitHub PR. Use when asked to make/update a Linear issue or ticket from a PR link, or to track a PR's work in Linear.
---

# Linear Issue from PR

## 1. Gather PR context

```bash
gh pr view <num> --repo <owner>/<repo> \
  --json title,body,url,number,author,state,mergedAt,isDraft,commits,files
```

## 2. Resolve team/project

- Team: default "Research" (ask only if it's obviously a different team).
- Project: ask via AskUserQuestion with options "RL Stack" / "Performance"
  (the built-in "Other" choice covers anything else). Skip asking only if
  the user already named the project in their request.

## 3. Draft the issue (show before creating)

- Title: PR title, conventional-commit prefix stripped if present.
- Description: 2-4 sentences on what/why from the PR body, ending with
  `PR: <url>`. Don't restate the diff.
- Status: isDraft -> In Progress; open, not draft -> In Review; merged -> Done.
  (If the user wants Backlog for a draft PR, they'll say so explicitly.)
- Label from conventional-commit type: feat -> Feature, fix -> Bug,
  refactor/chore/perf/docs -> Improvement; no match -> no label.
- Assignee: default "me". Don't ask -- assume it's Garrett's work unless
  the request says otherwise.
- Attach the PR with `links: [{url, title}]` on `save_issue` -- never
  `create_attachment` for a plain URL (that tool is for uploading file
  bytes: base64 + sha256).

## 4. Confirm, then create

Always show the full draft (team/project/title/description/status/label/
assignee/link) and wait for explicit go-ahead before calling `save_issue`.
Never create directly, even for a seemingly unambiguous request.

## 5. Report back

Return the created/updated issue's identifier and URL.

## Updating an existing issue

Pass `id` to `save_issue` instead of `team`/`title`, and only pass the
fields that actually changed. Do not blanket re-derive and re-pass
`labels` or `links` from the drafting rules above: `labels` replaces the
full label set (would wipe out any label added since creation), and
`links` is append-only (re-passing the same PR link duplicates it). A
common case: a PR referenced by an existing issue gets merged -- re-run
the status mapping above and pass only the updated `state`.

Still show the draft of what will change and wait for explicit go-ahead,
same as step 4. If you don't already have the issue's identifier from
context, ask the user for it rather than guessing.
