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
