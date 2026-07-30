# CLAUDE.md

Personal dotfiles repo (macOS + Linux): Neovim (Lua), zsh/bash, CLI tools.

**IMPORTANT**: This repo is public on GitHub. Always verify no API keys or secrets are committed.

## Setup

`./get_deps.sh` installs dependencies; `./install.sh` symlinks into `$HOME`.

## Neovim

- LSP: `lua/user/lsp/init.lua` (lua_ls, clangd, ruff, ty, tinymist), all five configured natively
  and listed explicitly in `vim.lsp.enable`. **nvim-lspconfig and mason-lspconfig are deliberately
  absent**: lspconfig shipped ~400 server configs that `automatic_enable` could start unasked, and
  mason-lspconfig existed only to install clangd, which `get_deps.sh` now pins. Every server must
  declare `filetypes`, since a config without it attaches to every buffer. Completion capabilities
  are **not** set here:
  blink.cmp's own `plugin/` file registers its delta via `vim.lsp.config("*")`, which nvim merges
  under every server. rust-analyzer is started by rustaceanvim via `vim.g.rustaceanvim` rather than
  `vim.lsp.enable`, but it still picks up that `"*"` block, so blink affects Rust too.
- Completion is blink.cmp (`lua/plugins/blink_cmp.lua`), pinned to `1.*` because `main` is an
  unstable v2 and the prebuilt Rust matcher is only downloaded on release tags. It replaced eight
  nvim-cmp plugins; only settings that diverge from a blink default live in that file.
- Formatting is conform.nvim via `<leader>cf`, and via `<leader>w`/`<leader>W` when `FORMAT_NVIM=1`.
  There is no `BufWritePre` hook, so plain `:w` never formats.
- `NVIM_APPNAME=nvim_min` uses `.config/nvim_min/`, which symlinks most of `.config/nvim/`.

## Shell

In login shells `.zprofile`/`.profile` run before `.commonrc`, which `.bashrc` and `.zshrc` source.
PATH and toolchain env belong in the profiles; `.commonrc` covers interactive shells. `RUSTUP_HOME`
is set in both on purpose, since neither alone reaches every shell type.

## Conventions

- Lua: `stylua`, 100 col, tabs (stylua's default; `.stylua.toml` sets only width). Use `prequire()`
  for plugin requires. New modules return an `M` table.
- Python: `ruff format`, `mypy`. Type hints required.
- Leader `<Space>`; LSP prefix `<leader>c`; git prefix `<leader>a`.
