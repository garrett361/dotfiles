---
name: prime-rl
description: Personal conventions for prime-rl work that the repo's own skills don't cover. Use when the user asks for end-to-end tests, A/B comparisons, parity checks, benchmarks, or any other measurement of a prime-rl change. Also use when reviewing a prime-rl PR or branch, or asked for an independent review of one.
---

# prime-rl conventions

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
