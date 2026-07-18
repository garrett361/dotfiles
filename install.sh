#!/bin/bash

mkdir -p ~/.config
mkdir -p ~/.claude
mkdir -p ~/.codex
is_linux=$(uname -s | grep -iq linux && echo 1 || echo 0)
# Link all config and script files to their expected locations.
for localdir in ".local" ".config"; do
	dirpath=$(readlink -f $localdir)
	ln -sfF $dirpath/* $HOME/$localdir
done

# symlink the global claude dir to ~/.claude. Need distinguishing name (claude_global) because `.claude/` in dotfiles repo is interpreted as repo-specific claude settings.
ln -sfF $(readlink -f claude_global)/* ${HOME}/.claude

# Link repo-managed Codex globals without replacing Codex runtime state or system skills.
ln -sfF "$(readlink -f codex_global/AGENTS.md)" "${HOME}/.codex/AGENTS.md"

mkdir -p "${HOME}/.codex/skills"
for skilldir in codex_global/skills/*/; do
	[ -d "$skilldir" ] || continue
	skillname=$(basename "$skilldir")
	skilltarget="${HOME}/.codex/skills/${skillname}"
	if [ -d "$skilltarget" ] && [ ! -L "$skilltarget" ]; then
		echo "Refusing to replace existing Codex skill directory: $skilltarget" >&2
		continue
	fi
	ln -snf "$(readlink -f "$skilldir")" "$skilltarget"
done

for localfile in ".commonrc" ".vimrc" ".bashrc" ".zshrc" ".profile" ".zprofile" ".stylua.toml" ".rg" ".ipython/profile_default/ipython_config.py" ".slurm_fns.sh" ".lsf_fns.sh"; do
    filepath=$(readlink -f $localfile)
	ln -sfF $filepath $HOME/$localfile
done

# git-tree: install as uv tool (editable, auto-discovered by git as `git tree`)
if command -v uv &>/dev/null; then
    uv tool install -e "$(cd git_tree && pwd)" 2>/dev/null || true
fi

# git-tree man page (makes `git tree --help` work via `man git-tree`). Absolute path: a fresh
# bootstrap may not have ~/.local/bin on PATH yet. Command is git_tree-owned; see git_tree/CLAUDE.md.
gt_bin="$HOME/.local/bin/git-tree"
[ -x "$gt_bin" ] && "$gt_bin" manpage --install &>/dev/null || true

vscode_settings=$(readlink -f settings.json)
if [ $is_linux -eq 1 ]; then
    echo "linux"
else
    ln -sfF $vscode_settings "$HOME/Library/Application Support/Code/User/settings.json"
fi
