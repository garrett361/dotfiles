# Evaluating reports and checkpoints

## First: is the stream terminal?

Classify against SKILL.md's terminal states. If not terminal, reply the same turn:

- **"slower than the baseline so far"**: the per-part breakdown it should measure, which part is implementation, two candidate designs, the target.
- **"out of registers / memory / bandwidth"**: whether the measurement shows a hardware limit or one design's layout; a design that changes the budget (split work across workers, reorder, recompute instead of store).
- **"the library can't"**: write the missing piece, patch the library locally, or use another library; measure each.
- **"needs the other stream first"**: you assign the dependency an owner or decide the interface; meanwhile the agent works on what it can.
- **"out of time" or a final report with time left, or simply stopping**: resume it with the next concrete step and the remaining time.
- **"not possible" for something obvious in principle**: the independent audit (SKILL.md, proven blocker) before you accept it.

## Questions for every report

- Which baseline, pinned how (commit, config, nodes, session)? Is it the one that matters to the user, or an intermediate step?
- Measured on the production path, or on an isolated benchmark that can flatter one side?
- Same session, same resources, same conditions for both arms?
- What data did it run on? A result checked only on random or synthetic inputs can reverse on real ones.
- Exactly equal to the reference, or a behavior or numerics change? If changed, measured against a trusted reference?
- What remains, and is each piece fundamental (measured against a bound) or implementation?
- Does another stream already have a design that removes this stream's barrier?

## Common fixable losses

Separate passes that could be fused into a neighbor; a copy, conversion or round trip that only exists because of an interface; a lost fusion the baseline had; synchronous waits the host does not need; untuned sizes or schedules; a fixed interface of a library treated as a law. None of these is a blocker.

## Wording a send-back

Name the design candidates (from other streams, the literature, an audit), the number you expect from each, the target and the next checkpoint. Credit what worked. Keep it to a few lines so the agent spends its context on the work.
