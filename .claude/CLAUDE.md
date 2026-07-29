# CLAUDE.md

Personal dotfiles repo (macOS + Linux): Neovim (Lua), zsh/bash, CLI tools.

**IMPORTANT**: This repo is public on GitHub. Always verify no API keys or secrets are committed.

## Setup

- `./get_deps.sh` installs dependencies; `./install.sh` symlinks dotfiles to `$HOME`
- Symlinks: `.config/*`, `.local/*`, `claude_global/*` -> `~/.claude`, `codex_global/` -> `~/.codex`, plus individual dotfiles (`.commonrc`, `.zshrc`, etc.)

## Neovim Architecture

- Entry point: `.config/nvim/init.lua` → loads `lua/user/` (keymaps, options, autocommands) + `lua/plugins/` (lazy.nvim)
- Shared utilities: `lua/nvim_utils/init.lua` — use `prequire()` for all plugin requires
- LSP config: `lua/user/lsp/init.lua` (lua_ls, clangd, ruff, ty, tinymist). mason-lspconfig auto-enables
  only what Mason installed, so clangd is listed explicitly in `vim.lsp.enable`. Rust is separate:
  rustaceanvim owns rust-analyzer via `vim.g.rustaceanvim` in `lua/plugins/rustaceanvim.lua`.
- Formatting: `lua/plugins/conform_and_lint.lua` (conform.nvim + nvim-lint). `<leader>cf` formats;
  `<leader>w`/`<leader>W` format then write when `FORMAT_NVIM=1`. Plain `:w` never formats.
- Snippets: `lua/user/snippets/` (LuaSnip, organized by filetype)
- Ftplugin overrides: `.config/nvim/ftplugin/`
- Minimal config: `NVIM_APPNAME=nvim_min` uses `.config/nvim_min/`

## Shell

- `.commonrc` sourced by both `.bashrc` and `.zshrc`: paths, aliases (`g`=git, `v`=nvim, `t`=tmux, `c`=claude), env vars (`$GITHUB`, `$DOTFILES`)
- `.zshrc`: fzf, starship; `^g` = tmux-sessionizer, `^f` = tmux-list-sessionizer, `^X^E` = edit command line
- Scripts in `.local/scripts/`

## Conventions

- Lua: `stylua` (`.stylua.toml` sets 100 col; indentation is stylua's default, tabs). Use `prequire()`
  for plugin requires.
- Python: `ruff format`, `mypy`. Type hints required.
- Leader: `<Space>`. LSP prefix: `<leader>c`. Git prefix: `<leader>a`.
- New Lua modules: return `M` table, place in `plugins/`, `user/`, or `nvim_utils/`.
