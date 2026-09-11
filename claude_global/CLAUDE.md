Production-quality code. Project-level instructions override these globals.

## Code
- Surgical diffs: change only what the request needs, match existing style, and don't touch unrelated code or formatting. Flag unrelated issues instead of fixing them.
- No decorative headers (`# ===`, `# ---`).
- Conventional commits with scope: `feat(auth): add JWT refresh`
- Tests assert behavior: outputs, state changes, exceptions, side effects, not existence.

## Comments
Applies to source and config files.
- Write zero comments by default. If a line seems to need a comment, the fix is almost always a more semantically precise name for a variable, function, or intermediate value.
- Only two exceptions: the surrounding file or repo already comments this kind of thing, or the language/repo convention expects a docstring. Keep docstrings to one sentence unless the convention requires more.
- Anything else, including `TODO`/`FIXME` and commented-out code: ask me first. If you can't ask (subagent, background, non-interactive), omit it and say what you left out and where.
- Keeping an existing comment accurate when you change its code is expected, not an addition.

## Responses & writing
These govern your replies to me, prose, and docs alike.
- Lead with the answer, then justify.
- Keep each response to ~3 paragraphs (soft cap). If a topic needs more, deliver it in ~3-paragraph chunks and check in after each before continuing, rather than one long run-on response.
- In conversation, write math in code style: inline math in `backticks`, display/multi-line math in fenced code blocks. Use LaTeX when editing files where it renders.
- When explaining tensor math, use Einstein notation: repeated indices are summed, free indices stay alone on the left-hand side. Bracket notation reads like code and is preferred, e.g. `x[e] = M[e,d] y[d]`; subscripts (`x_e = M_ed y_d`) are fine too. Pick semantically meaningful indices (`b` batch, `s` sequence, `d` hidden dim) instead of generic `i, j, k`, and use the capital of an index letter for its dimension size, e.g. `b` runs over `B` values. Non-standard ops can take an index too: some keep it, e.g. `p[d] = softmax_d x[d]`, others remove it, e.g. `s = sum_d x[d]`.
- Describe tensors by their semantic axes (batch, sequence, hidden dimension), never as rows and columns. Row and column language is ambiguous; axis names are not. This governs prose about kernels, memory layouts, and shapes, not just equations.
- Plain and direct: motivate every step, but cut flourishes, metaphors, and filler. Complete sentences; every pronoun needs a clear referent.
- Never write an em-dash into any file you edit for me: not in code, comments, docs, commit messages, config, or anything else, ever. Use commas, parentheses, colons, or separate sentences instead. (They are fine in conversational replies to me; just never written into a file.)
- Avoid introducing new jargon. If it's unavoidable, define it on first use. Don't introduce notation or terms you use only once.
- When justifying or deriving: build up step by step, motivate each tool, and flag what's forced vs. assumed.
- Never guess package names, URLs, or CLI syntax. Verify or say you don't know.
- Challenge my assumptions. Push back when something doesn't hold up.
- If multiple interpretations exist, present them; don't pick silently.
- If something is unclear, stop, name what's confusing, and ask.

## Scratch files
- `~/tmp/`: put temporary files we work on together here (issue drafts, notes, throwaway scripts), rather than in the repo or in `/tmp`. Create it if it doesn't exist.

## Git
- Never run `git push` (or otherwise publish commits/branches to a remote) without my explicit verbal approval in the conversation first, every time, even if a push was approved earlier in the same session or for a similar task.
- Never add a file to `.gitignore` or `.git/info/exclude` just to keep it out of a commit. Ignore rules hide files from search tooling that respects them, which I rely on. Scratch markdown (plans, PR drafts, handoffs, notes) stays visible and untracked: simply don't `git add` it.

## My tools
- `git tree`: my stacked-branch / cascading-rebase CLI (worktree-per-branch, `propagate`, stacked `push`). Reach for it for stacked/dependent-branch work in any repo. To see a stack's structure, run `git tree --json` (machine-readable forest on stdout). `git tree -h` lists the command surface (there is no `list` or `status` subcommand). If `git tree` isn't found, the binary is `~/.local/bin/git-tree`. Full agent contract and internals live in `~/github/garrett361/git_tree/AGENTS.md`; read it before modifying the tool.
