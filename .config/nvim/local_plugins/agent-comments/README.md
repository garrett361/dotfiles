# agent-comments

Comment on code in Neovim like a code review, then send the comments, with file:line and git
context, to a herdr agent.

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

## Tests

There is no plugin manager, no plenary and no busted: every external call is injected.

```
cd .config/nvim/local_plugins/agent-comments
nvim --headless --noplugin -u NONE -l tests/run.lua
```

It currently reports `54/54 passed`.

## Loading

`.config/nvim/lua/plugins/agent-comments.lua` loads this directory via a lazy.nvim `dir =` spec, so
it is never written to `lazy-lock.json`, never a `Lazy! clean` candidate, and skipped by
`Lazy! restore`.
