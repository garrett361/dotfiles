# Shared resources

- Split a machine's devices among agents explicitly (which devices each owns); one owner runs whole-machine jobs, or the orchestrator schedules windows for them and has the other agents stop by a stated time.
- Check every allocation before handing it out, and swap out anything that fails.
- Renew before expiry when the user granted it (record the grant); queue the successor on the same machines so agents keep their environment, and tell each agent the new handle when it starts.
- Release an allocation once no known work is left on it; but never cancel one early just to start its queued successor sooner, since the freed machines go to others' pending jobs.
- Never take resources other users' pending work needs, and never cancel others' jobs, except as the user's cluster rules explicitly allow.
- Lend an agent only the resources its brief granted; widening them later needs the user.

For GPU clusters: the profiling skill's `tools/agents.md` ("Allocations and GPUs") and `scripts/node_check.py`, plus the user's cluster memories.
