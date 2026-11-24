---
name: report
description: How to organize and write a report artifact that people will read, such as a study's findings, a decision record or a technical explainer. Use when writing, restructuring or revising one, or when the user says "/report". Not for PR descriptions (use pr-description), commit messages, code comments or chat replies. Covers content and structure; visual design, charts and diagram mechanics come from the artifact-design, dataviz and artifact-diagramming skills.
---

# Report

A reader should get the answer in the first screen and the evidence for it in the rest. The page has no length cap; the chat reply that delivers it stays short.

## Order

- Open with summary cards: three or four, each a short label, the answer in a few words, and one or two supporting lines. A reader who stops after the cards should know the conclusion. State each comparison in words a reader can act on without arithmetic ("7% slower than X", not "1.07x"); keep the ratio in the table.
- Lead every section with its main point in the first sentence, then give the evidence. Never build up to a conclusion. Rarely put more than one sentence of lead-in before a section's chart or table, and keep the text after it to a few lines; explanation the reader does not need for the result goes to the appendix or a collapsed block.
- When it matters, state the scope up front (what the numbers do and do not cover, including what each headline parameter means in practice, such as the data a sequence length holds), and close with what was not tested yet.
- Get the reader to the charts and tables fast. Side investigations, no-go explanations, per-run tables and history each get one line in a table or a bullet with a link to their source, never their own multi-paragraph or multi-table section, unless the user asks for one.
- Split the page into a main body and an appendix after a labeled divider. In the main body every element states a finding or shows the evidence for one. When the report reaches a conclusion or proposal, close the main body with a short "What would change the picture" section: each measurement or decision that would overturn or reorder it, the next step, and what it would change. Supporting material (method, robustness checks, history, how to reproduce, open questions) goes in the appendix.
- Keep the main body to the cards, one chart per finding, and at most three short bullets per section; a reader should finish it in about five minutes. Everything else goes in a collapsed table or the appendix. When the main body grows past that, cut before adding.
- When new results or corrections arrive, rewrite the affected section around the new finding instead of appending clauses or caveats, and re-read the whole page for anything the change made redundant. A superseded result gets one line in the appendix, not its old section.

## Show, then tell

- Assume every draft is too prose-heavy, and plan the figures before the text. For each finding, first ask which visual carries it (a chart of the measured series over steps or sizes, a breakdown bar, a heatmap, a timeline, a mechanism diagram); the runs' own metric files usually hold the data. Text is the lead line and the caption. On every revision, replace prose with a visual before adding anything.
- Draw a diagram for each mechanism the report explains. Use a table only for values a chart cannot carry, and prose last.
- Show a mechanism as cartoons in sequence: one panel per state, with each arrow labeled by the change between them.
- When the answer depends on a few quantities, map the decision space: put them on the axes, shade the regions (works, fails, does not fit), draw the boundary from a simple model, and place each concrete design as a point, with an arrow where a design moves.
- When several designs are compared, one strategy that often works is to draw each on the same skeleton (same lanes, same numbered steps) so only the differences change, with a short pros and cons list under each. Use it where it fits the comparison.
- Draw comparisons on one scale, with bars from zero, and align the axes of charts that show the same quantity (range, ticks and size) unless something serious precludes it. When a step is too small to see, label it, lay the bars out horizontally, or add a zoomed copy titled as zoomed.
- Put the full data behind a chart, and any detail the main text already summarizes, in a collapsed "Show as table" block right under it: the main line stays short and the evidence stays one click away.
- Compare against a reference design or a known baseline, so each number has something beside it.
- Order the rows of a comparison table or bar chart by the result, reference first, so the ranking reads top to bottom, and keep that order in every table and chart on the page.
- When items have a status (adopted, partial, ruled out, untried), color-code it the same way in every diagram and table, with hues that read in order and stay far apart.
- Mark measured against predicted everywhere, and say what a model was checked against and what it never was.
- Say which run, hardware and step a measured figure comes from.

## Words

- Keep prose light: short sentences, plain words, and bullets instead of a dense paragraph. Prefer spelling out a long comma-separated list as bullets, one item per line.
- Put qualifiers (one run, modeled, within noise) in a tag, a parenthesis or the collapsed table, not as extra clauses in the main sentence.
- Avoid jargon, including the project's internal names (code names, model-size and run labels, option labels, design letters, version tags): name a thing by what it does. When a term is unavoidable, define it inline at first use.
- A simple model that yields a rule of thumb is worth including: name the few quantities, write the formulas in a code-style block, plug in the numbers, and end with the rule.
- Give every number its unit and say whether it is measured or derived. Keep the same name for the same thing everywhere.
- When the report maximizes one quantity, state every effect in its unit throughout the main line of the report. A component's own units (an optimizer's time, a kernel's speedup) belong where that component is explained in detail.
- Prose and lists run the full width of the tables and figures, even where general design guidance suggests about 65 characters per line.

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
- Have a separate subagent read only for tone and length: blame, judgment words, claims stronger than the evidence, sections that do not lead with their point, and text a reader could skip.
- After assembling a page from pieces, check that its tags nest correctly.
- Fix what they confirm, then publish.

## Keeping this skill current

- This skill holds high-level guidance: how a report is ordered, what it shows, and how it is checked. Small wording or styling preferences (a particular phrasing, a number format) do not belong here: don't propose them, and propose cutting any that have crept in.
- While iterating on a report, when the user corrects something at that level that would likely recur, states a new preference at that level, or uses a report in a way this skill does not cover, offer a concrete edit: the proposed wording and the correction that prompted it. Raise it at a natural break, and edit or cut only after the user approves.
