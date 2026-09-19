# agent-comments

Comment on code in Neovim like a code review, then send the comments, with file:line context, to
an agent running under herdr or tmux.

## Provenance

This is a fork of the Lua half of [herdr-nvim](https://github.com/ChmaraX/herdr-nvim) at tag v1.0.1
by Adam Chmara, used under the MIT License. The full license text and copyright notice are in
`LICENSE` next to this file. **This code has been modified from the original.** Upstream's sidebar
and file picker are implemented in Rust and are not part of this fork.

## Changes

This list is the record of modification, and gets appended to as the fork diverges.

- Renamed throughout: module `herdr-nvim` to `agent-comments`, command `:Herdr` to `:AgentComment`,
  highlight groups `HerdrNvimComment{Sign,Text,Line}` to `AgentComments{Sign,Text,Line}`.
- Reformatted with this repo's stylua config, tabs at 100 columns.
- The plugin no longer defines keymaps. `M.config.prefix`, `M.config.keymaps` and the guard that
  skipped already-mapped keys are gone, and the maps are declared in the user's lazy spec instead.
  `M.statusline()` removed as unused.
- `agents.available()` added, and `agents.list()` gated on it: a missing `HERDR_WORKSPACE_ID` is now
  an error rather than a candidate list widened to every agent in every workspace. An agent's
  `status` is optional, since a multiplexer without an agent supervisor reports none, and
  `agents.display()` omits that segment when it is absent.
- Decorations moved to their own extmark namespace, separate from the one that tracks comment
  ranges, so a query of either namespace means exactly one thing.
- Prompt format rewritten: full snippets up to a 200-line cap with an explicit marker for what was
  omitted, a line number on every line, an `[unsaved]` marker for modified buffers, git context per
  comment instead of one first-comment-wins header, and a neutral terminator in place of the
  imperative footer.
- Prompt header and footer replaced by a single `N comment(s):` count line. The old header asserted
  a review intent the individual comments contradict, and its format note explained a convention
  `git blame` and `bat` already share. The count moved to the front because a truncated paste loses
  the end of the message, which is exactly where the old footer put it.
- The comment list restores the code window's buffer and view on cancel; `<CR>` jumps, `e` edits,
  `dd` deletes.
- Highlights are re-applied on `ColorScheme`, which previously wiped them, and
  `:checkhealth agent-comments` was added.
- The transport is split into `backends/herdr.lua` and `backends/tmux.lua` behind a selector that
  takes the first multiplexer whose session is live, herdr before tmux; `agents` and `dispatch`
  forward through it. The tmux backend lists the panes of the current session, keeps the ones whose
  title or current command matches a configured agent rule, resolves to the single candidate sharing
  the current window, and delivers through `set-buffer` plus `paste-buffer` so a multi-line prompt
  arrives as one paste instead of one submitted line per newline. `ui.pick_agent`'s empty-list
  message no longer names herdr, since either transport can produce it.
- The per-comment git context added earlier was removed, along with the `git` spawn and the
  per-directory cache behind it. The absolute path in each item header already identifies the repo,
  and the branch is one `git rev-parse` away in a tree the agent is already sitting in.
- Items are no longer numbered and the comment carries no `Comment:` label: an item is a
  column-zero `path:range` header, the quoted code, a blank line, then the comment text
  indented to the quoted-line column. Comments may span lines, and free-form ones often hold
  their own numbered lists, so column zero is reserved for the start of an item. `prompt.item`
  renders one item and `prompt.format` emits a `verbatim` item's text unchanged, so a
  pre-rendered item round-trips byte for byte.
- The comment list and the callout show `ui.summary(c)`, one line per comment: the first line plus
  a `(+N)` count of the lines it hides, or `❄ N lines verbatim` for a verbatim comment. Raw text
  cannot be used there at all, since `nvim_buf_set_lines` rejects an embedded newline and
  `virt_lines` silently renders one as garbage.
- Comment text is typed into a scratch float and committed with `:w`, in place of the single-line
  `vim.ui.input`, so a comment can run to several paragraphs and be edited before it is sent.
  `ui.input_comment(on_done, opts)` keeps `on_done` first (callers stub it by position) and now
  calls it on every exit path: the buffer joined by `\n` on a commit, `nil` on a cancel, raw, so
  `init.comment_range` drops a nil or whitespace-only result itself. The buffer is `acwrite` with
  a counter-based name, since `:w` on a `nofile` or unnamed buffer fails before `BufWriteCmd`
  fires; `bufhidden` is `wipe` and `BufWipeout` is the one teardown funnel. `q` and `<Esc>` are
  deliberately unbound and `<C-c>` cancels. `init.edit_comment` seeds the buffer with the
  comment's existing lines.
- `init.comment_range` anchors the comment when the editor opens, not when it is written:
  `comments.add(bufnr, start, end, nil)` records a draft, the callback then either
  `comments.edit`s the text in or `comments.delete`s the draft on a cancel. The editor can be left
  with `<C-w>w` to go read the code, so the window between picking the lines and writing the text
  is unbounded and editing in it is the point; plain line numbers held across it attach the
  finished comment to whatever has since moved under them. `comments.list` skips a draft, so it
  reaches neither the prompt nor the comment list, while `comments.get` and `comments.snippet`
  still resolve one. A draft is decorated with the rail alone: it is what shows which lines are
  being tracked while the user types, and `ui.summary` of an empty text is empty, so its callout
  would be a bubble that pushes the code down a line to say nothing.
- `<leader>zC` opens the same editor seeded with the fully rendered item (`prompt.item` of the
  draft), so the annotation can be written between two quoted code lines; what the buffer holds is
  stored and sent byte for byte. `comments.edit(id, text, { verbatim = true })` marks the entry and
  `resolve` reports it, which also freezes its `modified`: a snapshot's `[unsaved]` state is read
  back out of the stored text rather than from a buffer that may since have been written, because
  the prompt's preamble explains the markers the message actually shows. Nothing else parses that
  text. The list row, the preview jump and the sort order all keep coming from the live extmark, so
  rewriting or deleting the header line inside the block costs nothing.
- The comment text is no longer indented to the quoted-line column; it follows the blank line
  exactly as it was typed. The indent existed so that column zero marked the start of an item and
  a comment's own numbered list could not be read as one, and item numbering is gone, so an item
  now starts with a `path:range` header instead. A verbatim item was already sent as typed, and
  an ordinary one now is too.

- There is one kind of comment. `<leader>zc` seeds the editor with the rendered item (`prompt.item`
  of the draft, plus one empty line for the cursor to start on) whether it was started from the
  cursor line or from a visual selection, what the buffer holds is stored, and `prompt.format`
  emits it as typed: no `verbatim` flag, no `<leader>zC`, no second code path, and the editing
  experience no longer depends on which key made the comment.
  The cost is accepted knowingly: every comment is a snapshot, so one written before a large edit
  quotes and cites the file as it was. `comments.resolve` reads a committed comment's `[unsaved]`
  state back out of its stored text and a draft's from the live buffer, which is what its seed is
  rendered from. `ui.summary` is the block's line count, since the block is freely editable and any
  guess at which of its lines carries the annotation would eventually point at the wrong one.

## Tests

There is no plugin manager, no plenary and no busted: every external call is injected.

```
cd .config/nvim/local_plugins/agent-comments
nvim --headless --noplugin -u NONE -l tests/run.lua
```

## Loading

`.config/nvim/lua/plugins/agent-comments.lua` loads this directory via a lazy.nvim `dir =` spec, so
it is never written to `lazy-lock.json`, never a `Lazy! clean` candidate, and skipped by
`Lazy! restore`.
