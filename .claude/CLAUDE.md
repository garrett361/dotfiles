# CLAUDE.md

Personal dotfiles repo (macOS + Linux): Neovim (Lua), zsh/bash, CLI tools.

**IMPORTANT**: This repo is public on GitHub. Always verify no API keys or secrets are committed.

## Setup

- `./get_deps.sh` installs dependencies; `./install.sh` symlinks dotfiles to `$HOME`
- Symlinks: `.config/*`, `.local/*`, `.claude/*`, plus individual dotfiles (`.commonrc`, `.zshrc`, etc.)

## Neovim Architecture

- Entry point: `.config/nvim/init.lua` → loads `lua/user/` (keymaps, options, autocommands) + `lua/plugins/` (lazy.nvim)
- Shared utilities: `lua/nvim_utils/init.lua` — use `prequire()` for all plugin requires
- LSP config: `lua/user/lsp/init.lua` (Mason-managed: lua_ls, clangd, ruff, tinymist)
- Formatting: `lua/plugins/conform_and_lint.lua` (conform.nvim + nvim-lint); auto-format on save when `FORMAT_NVIM=1`
- Snippets: `lua/user/snippets/` (LuaSnip, organized by filetype)
- Ftplugin overrides: `.config/nvim/ftplugin/`
- Minimal config: `NVIM_APPNAME=nvim_min` uses `.config/nvim_min/`

## Shell

- `.commonrc` sourced by both `.bashrc` and `.zshrc`: paths, aliases (`g`=git, `v`=nvim, `t`=tmux, `c`=claude), env vars (`$GITHUB`, `$DOTFILES`)
- `.zshrc`: fzf, pyenv, starship; `^g` = tmux-sessionizer, `^f` = tmux-list-sessionizer
- Scripts in `.local/scripts/`

## Conventions

- Lua: `stylua` (100 col), 4-space indent. Use `prequire()` for plugin requires.
- Python: `ruff format`, `mypy`. Type hints required.
- Leader: `<Space>`. LSP prefix: `<leader>c`. Git prefix: `<leader>a`.
- New Lua modules: return `M` table, place in `plugins/`, `user/`, or `nvim_utils/`.
