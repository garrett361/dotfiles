# PRs relevant to the North Star

PRs in the public prime-rl repo that move toward, conflict with, or inform `north-star.md`. One line each. States go stale: refresh with `gh pr view <n> --json state` when reading, and update a row's note when a discussion changes how the PR relates to the design. Only public prime-rl PRs belong here: no private repos, artifacts, or internal document links. Keep under 100 lines.

| PR | Author | State | Relation to the North Star |
|---|---|---|---|
| #3963 | garrett361 | open | RL pipeline design doc; source of the pipeline invariants |
| #4065 | skpulipaka26 | merged | Trainer pulls batches; basis for "trainer pull is the commit point" |
| #4196 | mikasenghaas | merged | Training arrays kept by reference on env servers; first step to the rollout store |
| #4296 | mikasenghaas | open | Checkpoints in-flight and queued rollouts; informs live-state checkpointing |
| #3970 | faresobeid | open | Checkpoints queued samples and open groups; partial-group restore |
| #4297 | hallerite | open | Batch journal (to be replaced by the rollout store) and recoverable NCCL (open question) |
| #4326 | hallerite | open | Trainer recovery: restore from disk and admission; keep, extend with epochs |
| #4329 | hallerite | open | NIXL weight-transfer recovery |
| #4395 | hallerite | open | Inference recovery: `/ready` gating, membership at version boundaries; keep |
| #4397 | hallerite | open | vLLM failed-RPC reply drain; independent fix |
| #3971 | faresobeid | closed | Engine eviction and rejoin, router restart loop; reference design |
| #4273 | samsja | merged | Live orchestrator config update through the control API; basis for control endpoints |
| #4379 | skpulipaka26 | merged | Checkpoint action on the control API; basis for control endpoints |
