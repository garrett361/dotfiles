Production-quality code. Project-level instructions override these globals.

## Code
- Surgical diffs: change only what the request needs, match existing style, and don't touch unrelated code or formatting. Flag unrelated issues instead of fixing them.
- No decorative headers (`# ===`, `# ---`). Names over comments; comment only the *why*.
- Conventional commits with scope: `feat(auth): add JWT refresh`
- Tests assert behavior: outputs, state changes, exceptions, side effects — not existence.

## Responses & writing
These govern your replies to me, prose, and docs alike.
- Lead with the answer, then justify.
- Plain and direct: motivate every step, but cut flourishes, metaphors, and filler. Complete sentences; every pronoun needs a clear referent.
- Minimize em-dashes; prefer commas, parentheses, or separate sentences.
- Define jargon when you introduce it; don't introduce notation or terms you use only once.
- When justifying or deriving: build up step by step, motivate each tool, and flag what's forced vs. assumed.
- Never guess package names, URLs, or CLI syntax. Verify or say you don't know.
- Challenge my assumptions. Push back when something doesn't hold up.
- If multiple interpretations exist, present them; don't pick silently.
- If something is unclear, stop, name what's confusing, and ask.

## My tools
- `git tree`: my stacked-branch / cascading-rebase CLI (worktree-per-branch, `propagate`, stacked `push`). Installed globally; source in `~/github/garrett361/dotfiles/git_tree`. Reach for it for stacked/dependent-branch work in any repo; read `git_tree/CLAUDE.md` before modifying it.
