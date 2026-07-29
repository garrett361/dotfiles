# CLAUDE.md

Personal dotfiles repo (macOS + Linux): Neovim (Lua), zsh/bash, CLI tools.

**IMPORTANT**: This repo is public on GitHub. Always verify no API keys or secrets are committed.

## Setup

`./get_deps.sh` installs dependencies; `./install.sh` symlinks into `$HOME`.

## Neovim

- LSP: `lua/user/lsp/init.lua` (lua_ls, clangd, ruff, ty, tinymist). mason-lspconfig auto-enables
  only what Mason installed, so clangd needs an explicit `vim.lsp.enable`. rust-analyzer is owned
  by rustaceanvim through `vim.g.rustaceanvim`, not this file.
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
