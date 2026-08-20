#!/bin/bash

# Every path below is relative to the repo, and some of them gate an rm, so anchor the cwd rather
# than trusting the caller's.
cd "$(dirname "$0")" || exit 1

mkdir -p ~/.claude
mkdir -p ~/.codex

# Clear the destination and link to an exact path; handing ln a destination directory is not
# portable. Real directories are left alone: they belong to other installers.
link_entry() {
	local src="$1" dest="$2"
	[ -e "$src" ] || return 0
	if [ -d "$dest" ] && [ ! -L "$dest" ]; then
		echo "Refusing to replace existing directory: $dest" >&2
		return 1
	fi
	rm -f "$dest"
	ln -sf "$src" "$dest"
}

# Drop links whose target no longer exists in the repo. link_entry below only overwrites paths it
# still creates, so removing a config dir here would otherwise leave a dangling link forever.
for localdir in ".local" ".config"; do
	for link in "$HOME/$localdir"/*; do
		[ -L "$link" ] && [ ! -e "$link" ] && rm -f "$link"
	done
done

# Link all config and script files to their expected locations.
for localdir in ".local" ".config"; do
	mkdir -p "$HOME/$localdir"
	for entry in "$(readlink -f "$localdir")"/*; do
		link_entry "$entry" "$HOME/$localdir/$(basename "$entry")"
	done
done

# Link a repo skills dir into a harness skills dir one entry at a time, never as a whole. A
# harness skills dir is a shared namespace that other installers also write into (`git tree skills
# --install`, `claude plugin init`); linking the repo dir itself would make this repo *be* that
# namespace, so their machine-specific output would land here as untracked files.
link_skills() {
	local src_dir="$1" dest_dir="$2" skilldir name
	[ -d "$src_dir" ] || return 0
	# The harness dir itself must be real, or the per-entry links below land inside the repo.
	[ -L "$dest_dir" ] && rm -f "$dest_dir"
	mkdir -p "$dest_dir"
	for skilldir in "$src_dir"/*/; do
		[ -d "$skilldir" ] || continue
		name=$(basename "$skilldir")
		link_entry "$(readlink -f "$skilldir")" "$dest_dir/$name"
	done
}

# symlink the global claude dir to ~/.claude. Need distinguishing name (claude_global) because `.claude/` in dotfiles repo is interpreted as repo-specific claude settings.
# `skills` is skipped here and handled by link_skills, which keeps the harness dir real.
for entry in "$(readlink -f claude_global)"/*; do
	[ "$(basename "$entry")" = "skills" ] && continue
	link_entry "$entry" "${HOME}/.claude/$(basename "$entry")"
done

# A harness dir that is (or was) a link to one of these puts other installers' output in the repo.
# Repo skills are real directories, so a symlink here is always someone else's and safe to drop.
for repo_skills in claude_global/skills agents_global/skills; do
	for entry in "$repo_skills"/*; do
		[ -L "$entry" ] && rm -f "$entry"
	done
done

link_skills "$(readlink -f claude_global/skills)" "${HOME}/.claude/skills"

# Link repo-managed Codex globals without replacing Codex runtime state or system skills.
link_entry "$(readlink -f codex_global/AGENTS.md)" "${HOME}/.codex/AGENTS.md"

# ~/.agents/skills is the cross-tool location, hence agents_global rather than a Codex-specific
# name: nothing under it is Codex-only.
link_skills "$(readlink -f agents_global/skills)" "${HOME}/.agents/skills"

# Codex also reads $CODEX_HOME/skills, which it marks deprecated. Keep no repo-managed links there
# or every skill shows up twice. Anything else in that directory, notably Codex's own .system, is
# left alone.
dotfiles_root="$(pwd -P)"
for link in "${HOME}/.codex/skills"/*; do
	[ -L "$link" ] && [[ "$(readlink "$link")" == "$dotfiles_root"/* ]] && rm -f "$link"
done

for localfile in ".commonrc" ".vimrc" ".bashrc" ".zshrc" ".profile" ".bash_profile" ".zprofile" ".stylua.toml" ".rg" ".slurm_fns.sh" ".lsf_fns.sh"; do
	link_entry "$(readlink -f "$localfile")" "$HOME/$localfile"
done

# ~/.ssh stays machine-local (keys, known_hosts, host aliases), so link the one file the repo owns
# rather than the directory. sshd runs it for every session, the only hook that fires for
# `ssh host <cmd>` and `ssh -t host tmux attach`, which never source a profile.
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
link_entry "$(readlink -f .ssh/rc)" "$HOME/.ssh/rc"

# git-tree: install as uv tool (editable, auto-discovered by git as `git tree`) from the sibling
# repo cloned by get_deps.sh. --force keeps re-pointing deterministic; warn loudly if it's missing.
gt_src="$(cd "$(dirname "$0")/../git_tree" 2>/dev/null && pwd)"
if command -v uv &>/dev/null && [ -n "$gt_src" ]; then
    uv tool install -e "$gt_src" --force
elif command -v uv &>/dev/null; then
    echo "git_tree sibling missing at ../git_tree — run ./get_deps.sh first" >&2
fi

# git-tree man page (makes `git tree --help` work via `man git-tree`). Absolute path: a fresh
# bootstrap may not have ~/.local/bin on PATH yet. Command is git_tree-owned; see ../git_tree/CLAUDE.md.
gt_bin="$HOME/.local/bin/git-tree"
[ -x "$gt_bin" ] && "$gt_bin" manpage --install &>/dev/null || true

# git-tree agent skills, linked into ~/.claude/skills and ~/.agents/skills. Command is
# git_tree-owned; see ../git_tree/AGENTS.md. stdout is noise on a bootstrap, but stderr is kept:
# the command refuses rather than overwrite a path it did not write, and a silent refusal would be
# indistinguishable from a successful install.
[ -x "$gt_bin" ] && "$gt_bin" skills --install >/dev/null || true

# Restore nvim plugin state from lazy-lock.json.
nvim_bin="$HOME/.local/bin/$(uname -m)/nvim"
[ -x "$nvim_bin" ] || nvim_bin=$(command -v nvim)
if [ -x "$nvim_bin" ]; then
	for appname in nvim nvim_min; do
		[ -d "$HOME/.config/$appname" ] || continue
		NVIM_APPNAME="$appname" "$nvim_bin" --headless "+Lazy! restore" +qa </dev/null
	done
else
	echo "nvim not found; skipping plugin restore (run ./get_deps.sh first)" >&2
fi

# Skipped when VS Code has never run, since ln cannot create the parent directory itself.
vscode_dir="$HOME/Library/Application Support/Code/User"
if [ "$(uname -s)" = "Darwin" ] && [ -d "$vscode_dir" ]; then
	link_entry "$(readlink -f settings.json)" "$vscode_dir/settings.json"
fi
