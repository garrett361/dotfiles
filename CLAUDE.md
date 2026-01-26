# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a personal dotfiles repository for managing configuration files across macOS and Linux environments. The primary focus is on Neovim configuration (Lua), shell configuration (zsh/bash), and various CLI tool configurations.

IMPORTANT: this dotfiles repo is expected to be publicly available on github, so it is extremely important to always verify the absence of accidental API key leaks or similar security issues.

## Installation & Setup

### Installing Dotfiles
```bash
# Install dependencies (brew on macOS, manual on Linux)
./get_deps.sh

# Symlink dotfiles to home directory
./install.sh
```

The `install.sh` script symlinks files from this repository to `$HOME`, creating the following links:
- `.config/*` → `$HOME/.config/`
- `.local/*` → `$HOME/.local/`
- `.claude/*` → `$HOME/.claude/`
- Individual dotfiles (`.commonrc`, `.vimrc`, `.bashrc`, `.zshrc`, `.gitignore_global`, `.stylua.toml`, `.rg`)

### Minimal Neovim Config
Set `export NVIM_APPNAME=nvim_min` to use the minimal nvim config located at `.config/nvim_min/`.

## Key Environment Variables

From `.commonrc`:
- `$GITHUB` - Points to `$HOME/github`
- `$DOTFILES` - Points to `$GITHUB/garrett361/dotfiles`
- `$EDITOR` - Set to `nvim` with `PYTHONPATH=$PYTHONPATH:$PWD`
- `$RIPGREP_CONFIG_PATH` - Points to `$HOME/.rg`

## Neovim Configuration Architecture

### Configuration Entry Point
- **Main config**: `.config/nvim/init.lua`
  - Loads user configs from `.config/nvim/lua/user/` (keymaps, options, autocommands, user_commands)
  - Uses lazy.nvim plugin manager to load plugins from `.config/nvim/lua/plugins/`
  - Conditionally skips plugins when running in VSCode

### Core Module: `nvim_utils`
Located at `.config/nvim/lua/nvim_utils/init.lua`, this module provides:
- `prequire()` - Protected require with error messages
- Visual mode utilities (`is_visual_mode()`, `get_vis_pos()`, `get_vis_text()`)
- String/table utilities (`slice()`, `string_to_args()`)
- Buffer utilities (`get_visible_buffers()`)

Submodules under `nvim_utils/`:
- `marks/` - Custom mark utilities
- `typst/` - Typst language support
- `table/` - Table manipulation
- `exec/` - Execution utilities
- `os/` - OS-specific utilities
- `ts/` - Treesitter utilities
- `str/` - String utilities

### Language Server Configuration
- **LSP setup**: `.config/nvim/lua/user/lsp/init.lua`
- Uses Mason for LSP installation
- Configured LSPs:
  - `lua_ls` - Lua (with Neovim runtime awareness)
  - `clangd` - C/C++/CUDA (with inlay hints)
  - `ruff` - Python (linting only, formatting disabled)
  - `tinymist` - Typst

### Formatting & Linting
- **Config**: `.config/nvim/lua/plugins/conform_and_lint.lua`
- **Formatters** (via conform.nvim):
  - Python: `ruff_format` (preferred) or `black` + `isort` (fallback)
  - Lua: `stylua`
  - C/C++/CUDA: `clang_format`
  - Markdown: `prettier` + `injected`
  - JSON/YAML/HTML/JS: `prettier`
  - Typst: `typstyle`
- **Linters** (via nvim-lint):
  - Python: `mypy`
- **Auto-format on save**: Controlled by `FORMAT_NVIM` environment variable
  - When `FORMAT_NVIM=1`, format and lint on `<leader>w` and `<leader>W`

### Plugin Organization
All plugins live in `.config/nvim/lua/plugins/` as individual Lua files. Key plugins:
- `fzf_lua.lua` - Fuzzy finding
- `mini.lua` - Collection of mini.nvim modules
- `cmp.lua` - Autocompletion
- `luasnip.lua` - Snippet engine
- `gitsigns.lua` - Git integration
- `oil.lua` - File explorer
- `codecompanion.lua` - AI assistance

### Filetype-Specific Settings
Located in `.config/nvim/ftplugin/` - per-filetype overrides for c, cpp, cuda, markdown, tex, and typst.

### Snippets
Located in `.config/nvim/lua/user/snippets/` (20+ files), using LuaSnip format. Organized by filetype (python, lua, markdown, tex, etc.).

### Keymaps
Main keymaps in `.config/nvim/lua/user/keymaps.lua`:
- Leader key: `<Space>`
- LSP keybindings under `<leader>c` prefix (see `.config/nvim/lua/plugins/lsp.lua`)
- Format: `<leader>cf`
- Save with format: `<leader>w`
- Save and quit with format: `<leader>W`

## Shell Configuration

### Common RC (`.commonrc`)
Sourced by both `.bashrc` and `.zshrc`, contains:
- Path setup (`$HOME/.local/bin`, `$HOME/.local/scripts`)
- Aliases: `g` (git), `v` (nvim), `ll`, `..`, `...`, `cddot`, `cdg`, `t` (tmux), `c` (claude)
- Functions: `mcd`, `mkfile`, `gc`, `dotfiles_rebase`
- OpenShift/Kubernetes aliases: `l`, `d`, `de`, `dp`, `r` (wrapper scripts)

### Zsh-Specific (`.zshrc`)
- Large history configuration (10M entries, shared across sessions)
- API key loading from `$DOTFILES/API_KEYS/`
- Bindkeys: `^g` (tmux-sessionizer), `^f` (tmux-list-sessionizer), `^X^E` (edit-command-line)
- Integrations: fzf, pyenv, starship prompt

## Custom Scripts

Located in `.local/scripts/`:
- `tmux-sessionizer` - FZF-based tmux session creation from `$GITHUB` directories
- `tmux-list-sessionizer` - Switch between existing tmux sessions
- `oc_*` scripts - OpenShift/Kubernetes helpers (oc_logs, oc_delete, oc_describe, oc_rsh, oc_exec)

## Development Workflow

### Editing Neovim Config
When modifying Neovim configuration:
1. Changes to plugin files (`.config/nvim/lua/plugins/*.lua`) require `:Lazy reload <plugin>` or nvim restart
2. Changes to user files (`.config/nvim/lua/user/*.lua`) may require `:source $MYVIMRC` or restart
3. LSP changes in `.config/nvim/lua/user/lsp/init.lua` require `:LspRestart`

### Testing Formatting
```bash
# Enable auto-format on save
export FORMAT_NVIM=1

# Then in nvim, <leader>w will format before saving
```

### Lua Module Pattern
When creating new Neovim Lua modules:
- Use `require("nvim_utils").prequire("module_name")` for safe requires
- Return a table `M` with functions
- Place in appropriate location:
  - Plugins: `.config/nvim/lua/plugins/`
  - User configs: `.config/nvim/lua/user/`
  - Utilities: `.config/nvim/lua/nvim_utils/`

### Working with Dotfiles
```bash
# Update dotfiles and rebase on main
dotfiles_rebase

# Navigate to dotfiles
cddot
```

## Platform-Specific Notes

### macOS
- Uses Homebrew for package management
- Aerospace window manager configured in `.config/aerospace/`
- VS Code settings symlinked from `settings.json`

### Linux
- Manual tool installation in `$HOME/.local/bin/` (ripgrep, neovim, delta, bat, fd, gh)
- Rust tools via cargo (tree-sitter-cli, starship)
- i3 window manager configured in `.config/i3/`

## File Types & Conventions

### Lua
- Format with `stylua` (config: `.stylua.toml`, column width: 100)
- LSP: `lua_ls` with Neovim runtime awareness
- 4 spaces for indentation (expandtab enabled)

### Python
- Format with `ruff format` or `black` (88 char line length)
- Lint with `ruff` and `mypy`
- Type hints required for LSP

### General
- Default textwidth: 100 (from `options.lua`)

### Markdown
- Format with `prettier` + injected code block formatting

## Important Conventions

1. **Protected Requires**: Always use `prequire()` for plugin requires to get helpful error messages
2. **Leader Key**: `<Space>` - all custom keymaps use `<leader>` prefix
3. **LSP Prefix**: `<leader>c` for all LSP-related commands
4. **Git Prefix**: `<leader>a` for git/gitsigns commands (stage, reset, preview, navigate hunks)
5. **Format on Save**: Opt-in via `FORMAT_NVIM=1` environment variable
6. **Tmux Integration**: `^g` from shell to create new tmux sessions via FZF
