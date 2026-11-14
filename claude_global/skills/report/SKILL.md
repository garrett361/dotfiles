---
name: report
description: How to organize and write a report artifact that people will read, such as a study's findings, a decision record or a technical explainer. Use when writing, restructuring or revising one, or when the user says "/report". Not for PR descriptions (use pr-description), commit messages, code comments or chat replies. Covers content and structure; visual design, charts and diagram mechanics come from the artifact-design, dataviz and artifact-diagramming skills.
---

# Report

A reader should get the answer in the first screen and the evidence for it in the rest. The page has no length cap; the chat reply that delivers it stays short.

## Order

- Open with summary cards: three or four, each a short label, the answer in a few words, and one or two supporting lines. A reader who stops after the cards should know the conclusion.
- Lead every section with its main point in the first sentence, then give the evidence. Never build up to a conclusion.
- When it matters, state the scope up front (what the numbers do and do not cover), and close with what was not tested yet.
- Split the page into a main body and an appendix after a labeled divider. In the main body every element states a finding or shows the evidence for one, ending with what would change the conclusion or the next step. Supporting material (method, robustness checks, history, how to reproduce, open questions) goes in the appendix.

## Show, then tell

- Draw a diagram for each mechanism the report explains. Use a table only for values a chart cannot carry, and prose last.
- Show a mechanism as cartoons in sequence: one panel per state, with each arrow labeled by the change between them.
- When the answer depends on a few quantities, map the decision space: put them on the axes, shade the regions (works, fails, does not fit), draw the boundary from a simple model, and place each concrete design as a point, with an arrow where a design moves.
- Draw comparisons on one scale, and add a zoomed copy when one part is too small to see.
- Compare against a reference design or a known baseline, so each number has something beside it.
- Mark measured against predicted everywhere: a callout where predictions begin, filled against hollow points, dashed lines where a regime changes. Say what a model was checked against and what it never was.
- Label a schematic as not to scale, and say which run, hardware and step a measured figure comes from. Keep a chart's numbers in a collapsed table beneath it.

## Words

- Keep prose light: short sentences, plain words, and bullets instead of a dense paragraph.
- Use plain words over jargon. When a term is unavoidable, define it inline at first use, and don't coin a term used only once.
- A simple model that yields a rule of thumb is worth including: name the few quantities, write the formulas in a code-style block, plug in the numbers, and end with the rule.
- Give every number its unit and say whether it is measured or derived. Keep the same name for the same thing everywhere.
- Prose and lists run the full width of the tables and figures, even where general design guidance suggests about 65 characters per line: set the width once on the content wrapper and give `p`, `ul` and `ol` no `max-width`.

## Terms

- Avoid a terms table when inline definitions suffice. When one is needed, put it at the end of the appendix, and add a line near the top that links to it.

## Links

- Hyperlink everything a reader might open: branches, PRs, issues, commits, files, papers, docs and run pages. Pin code links to a commit, down to the line where it matters.
- Every in-page reference ("see Memory", "the figure above") is a link to its anchor.
- When a link target is not pushed or published yet, say so instead of leaving a link that will not resolve.

## Tone

- Facts and analysis only: say what the code and the measurements show, not who got something wrong.
- Describe earlier results by what they measured and under which conditions, then how the new numbers relate.
- Mark hypotheses and estimates as such.

## Before publishing

- Have a subagent check every number and derived claim against the data and the code that produced it. Give it the claims and file pointers, not your conclusions, and ask for OK or WRONG with evidence; repo docs can be wrong.
- Have a separate subagent read only for tone: blame, judgment words (mistakenly, failed, broken) and claims stronger than the evidence.
- Fix what they confirm, then publish.
