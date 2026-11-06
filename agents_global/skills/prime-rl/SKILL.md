---
name: prime-rl
description: Personal conventions for prime-rl work that the repo's own skills don't cover. Use when the user asks for end-to-end tests, A/B comparisons, parity checks, benchmarks, or any other measurement of a prime-rl change. Also use when reviewing a prime-rl PR or branch, or asked for an independent review of one. Also use when discussing or reviewing the RL system's design, resilience, or component responsibilities. Also use before pushing or posting anything to the public prime-rl repo.
---

# prime-rl conventions

- **Hard rule: nothing private goes public.** prime-rl is a public repo. Anything pushed or posted to it
  (commits and branch files, including `benchmarks/scripts/`; PR descriptions; review bodies and inline
  comments; issues) must not name internal or unreleased models, internal run names or IDs, private W&B or
  dashboard links, cluster names or hostnames, private repos, internal documents, or customers and partners,
  and must not contain credentials or tokens. Before each push or post, check the exact text and files
  for these, and ask the user when something might be private.
- **Testing code goes in the branch history:** every file a test or benchmark uses to produce reported
  results (configs, drivers, mocks or patches, analysis scripts, the report and result tables) is committed
  to the branch under test, under `benchmarks/scripts/<topic>/`. If it should not ship, delete it in a
  later commit. Never rebase or amend it away. This keeps the code behind every reported number reachable
  at a commit, which a squash merge still leaves out of `main`. Link the adding commit from the PR
  description where the results are discussed.
- `e2e.md`: workloads, run hygiene, and reporting for end-to-end A/B tests of trainer changes. Read it when the
  user asks for end-to-end tests.
- `review.md`: how to review a prime-rl PR branch, including a follow-up on the user's earlier comments. Read it
  when the user asks for a review of a PR or the checked-out branch.
- `north-star.md`: the currently agreed big-picture design of the RL system. Read it before design discussions and before reviewing pipeline or resilience changes; update it, with a dated Decision log line, when a design decision is agreed.
- `invariants.md`: desired invariants with status. Cross-reference designs and PRs against it, and update statuses as code changes.
- North Star docs stay short, high level and human readable: no internal model or run names, no links to private repos, artifacts or internal documents (only public prime-rl PRs), no hard-to-verify measurements, at least one summarizing ASCII diagram per design doc (not the invariants list), and if a doc passes 100 lines, discuss simplifying or splitting it before adding more.
- `prs.md`: public prime-rl PRs relevant to the North Star, with their relation to it. Refresh states when reading and update notes as discussions conclude.
