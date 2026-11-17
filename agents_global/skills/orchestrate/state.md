# Orchestrator state

Keep the round on disk before you need it: your context can be summarized or branched at any time. Keep the files in one directory outside every agent's worktree (scratch space), and name that directory in the shared brief.

## Three files

- **Registry**: the owning session's id; per stream: agent id, task, branch and worktree, resources and hard stop, next checkpoint, target, current best, state (working or a terminal state). Also the compute ledger: per allocation, its handle, its devices or machines, the owner of each slice, and its expiry. Update it on every launch, checkpoint, relay and release.
- **Decisions**: every user decision, verbatim when it grants authority (pushes, resources, scope, adopting changes), with the time.
- **Recovery state**: open questions for the user, pending relays, scheduled reminders and what each one does, and the handoff option at round end.

Agents' progress and findings files live beside these.

## Resuming

After a summary of your context, or in a branched or new session:

1. Reread the three files and the shared brief.
2. Reconcile with reality before acting: the job queue, each worktree's `git status` and `git log`, each agent's last message.
3. If another live session owns the agents, stop and ask the user; two orchestrators driving the same agents corrupt state.

Agents' messages and scheduled reminders belong to the session that launched them; a new session cannot receive them. At round end, if your context is degraded, hand the remaining steps (reviews, the summary, and pushes only with the user's explicit approval for each) to a fresh session through these files, for example with git-tree-plan.
