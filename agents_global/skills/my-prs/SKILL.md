---
name: my-prs
description: List open PrimeIntellect-ai PRs that are assigned to the user, request their review, or that they have already reviewed, as titles plus plain URLs. Use when the user says "/my-prs", "what PRs am I assigned to", "PRs waiting on me", or wants to keep track of PRs that need them.
---

# My PRs

Run this skill's `scripts/my_prs.sh`. It prints one PR per line as `title<TAB>url`, covering open PRs where the user is the assignee, a requested reviewer, or a past reviewer, in the repos listed in its `REPOS` array.

Print each PR as its title followed by its bare URL on the next line, with a blank line between PRs. Do not format the URL as a markdown link, so it copy-pastes cleanly. Add no other commentary.

If the script prints nothing, say there are no open PRs assigned to the user.

To cover another repo, add its name to `REPOS` in the script.
