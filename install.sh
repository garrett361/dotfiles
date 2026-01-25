#!/bin/bash

mkdir ~/.config
is_linux=$(uname -s | grep -iq linux && echo 1 || echo 0)
# Link all config and script files to their expected locations.
for localdir in ".local" ".config"; do
	dirpath=$(readlink -f $localdir)
	ln -sfF $dirpath/* $HOME/$localdir
done

# symlink the global claude dir to ~/.claude. Need distinguishing name (claude_global) because `.claude/` in dotfiles repo is interpreted as repo-specific claude settings.
dirpath=$(readlink -f $localdir)
ln -sfF $(readlink -f claude_global)/* ${HOME}/.claude

for localfile in ".commonrc" ".vimrc" ".bashrc" ".zshrc" ".gitignore_global" ".stylua.toml" ".rg" ".ipython/profile_default/ipython_config.py"; do
    filepath=$(readlink -f $localfile)
	ln -sfF $filepath $HOME/$localfile
done

vscode_settings=$(readlink -f settings.json)
if [ $is_linux -eq 1 ]; then
    echo "linux"
else
    ln -sfF $vscode_settings "$HOME/Library/Application Support/Code/User/settings.json"
fi
