# RL system North Star

The desired big-picture design of the prime-rl RL system, as currently agreed. This is a living document: undecided items stay under Open questions, and each agreed decision gets a dated line in the Decision log. Keep it short and high level; if it passes 100 lines, discuss simplifying or splitting it. Desired invariants live in `invariants.md`.

## Goals

- Every component can fail and be replaced independently, without restarting the others. Kubernetes is the primary target; SLURM stays usable.
- A restart should not discard completed work or force a long warm-up of the rollout pipeline.
- Components interact through narrow, explicit contracts (handles and small messages), not shared marker files or in-memory assumptions about each other.

## Overview

```
                               RUN CONTROLLER
          (operator actions; health, ready and control endpoints on every component)

 ORCHESTRATOR --task requests--> ENV DISPATCHER --> ENV SERVERS --model calls--> ROUTER --> INFERENCE
   ^     |                                              |                                        ^
   |     | manifests: rollout IDs + metadata            | completed rollouts                     |
   |     v                                              v                                        |
   |  TRAINER <======= heavy data, pulled once ======= ROLLOUT STORE (per node, disk-backed)      |
   |     |                                              |                                        |
   +-----|------------- rollout metadata <--------------+                                        |
         +------------------------- publishes weights (epoch, version) --------------------------+
```

## Components

- Orchestrator: picks tasks and runs the curriculum, tracks groups, assembles batches and places them on trainer ranks from metadata only, rate-limits itself from an external load signal, and owns staleness policy. It holds no per-token data.
- Env dispatcher: decides which env server runs each episode, the env-side counterpart of the inference router.
- Env servers: run episodes (agent loop, tools, sandboxes, scoring) and hand completed rollouts to the local rollout store.
- Rollout store: one per node beside the env servers. Holds completed rollouts, persists them asynchronously, serves them to trainers, cleans them up, and exports traces.
- Router and inference: serve model calls; inference installs published weight versions.
- Trainer: pulls the rollouts in its manifest and derives all per-token data itself (advantages, masks, corrections).
- Run controller: operator front door for actions that span components; each component also exposes its own control endpoints.

## Data plane

- Rollout data moves by handle; heavy data crosses the network to the trainer once.
- A trainer pull is the commit point: a pulled rollout leaves the store's available pool.
- On a trainer rollback, the store refreshes from disk everything a committed checkpoint does not yet cover. Replay is valid, not exact.
- Store entries are deleted once a committed trainer checkpoint covers them, or once dropped.
- The orchestrator rebuilds its state by re-polling the stores; partial groups are restored by task reference and re-dispatch only their missing members.
- The store interface is key-value shaped with explicit durability, so other backends can replace the default.

## Weights and identity

- A policy is identified by `(epoch, version)`; the epoch increases whenever a trainer restore recomputes already-published versions. Writes and pulls from an older epoch are rejected.
- NCCL broadcast is the steady-state weight path; group membership changes only at version boundaries. A durable copy serves joiners and recovery.

## Health

- A component exits on its own when it knows it is broken.
- Every component exposes `/health` (progress-aware) and `/ready`; supervisors act on them. SLURM stays exit-based, with manual control endpoints.

## Open questions

- Who decides when inference switches weight versions: the orchestrator, or inference on arrival with the orchestrator only enforcing staleness.
- Mid-transfer NCCL abort versus process restart and reload.
- How several trainer ranks read the same rollout (one rank pulls and shares, or ref-counted slice pulls).
- Keeping heavy per-token arrays at the inference engine instead of sending them to env servers.
- Live-state checkpointing of in-flight episodes and sandboxes.
- Restarting a component, such as the trainer, with new source code mid-run.

## Decision log

- 2026-11-05: Rollout data moves by handle; heavy data goes from rollout store to trainer once.
- 2026-11-05: Rollout store is a separate per-node process beside the env servers; env servers keep only episode work.
- 2026-11-05: Trainer pull is the commit point; rollback refreshes from disk; replay is valid, not exact.
- 2026-11-05: Orchestrator decides from metadata only; the trainer derives all per-token data.
- 2026-11-05: Policy identity is `(epoch, version)`. Soft decision: rollouts from a previous epoch are accepted, with a divergence metric logged after recovery.
- 2026-11-05: NCCL stays the steady-state weight path; membership changes only at version boundaries.
- 2026-11-05: Partial groups are restored by task reference, guarded by a taskset fingerprint.
- 2026-11-05: Components self-exit when certain; `/health` and `/ready` everywhere; SLURM stays exit-based.
- 2026-11-05: Each component exposes its own control endpoints; a run controller owns cross-component actions.
- 2026-11-05: Live-state checkpointing of in-flight episodes and sandboxes moved into nearer-term scope.
