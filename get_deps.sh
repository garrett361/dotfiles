#!/bin/bash

is_linux=$(uname -s | grep -iq linux && echo 1 || echo 0)
arch=$(uname -m)

# Arch-specific bin dir so x86 and ARM installs don't collide on a shared home
bin_dir=$HOME/.local/bin/$arch

if [ ! -d $bin_dir ]; then
    mkdir -p $bin_dir
fi


# fzf: clone to arch-specific dir; --bin skips generating ~/.fzf.bash/zsh (we source directly)
[ -d "$HOME/.fzf-$arch" ] || git clone --depth 1 https://github.com/junegunn/fzf.git "$HOME/.fzf-$arch"
"$HOME/.fzf-$arch/install" --bin

# Claude Code
# Wipe existing versions so the installer always copies the arch-correct binary
# (the claude `install` subcommand skips copying if the version already exists)
rm -f "$HOME/.local/share/claude/versions"/*
curl -fsSL https://claude.ai/install.sh | bash
if [ "$is_linux" -eq 1 ]; then
    if [ -L "$HOME/.local/bin/claude" ]; then
        claude_real=$(readlink -f "$HOME/.local/bin/claude")
        version=$(basename "$claude_real")
        mkdir -p "$HOME/.local/share/claude-$arch/versions"
        cp "$claude_real" "$HOME/.local/share/claude-$arch/versions/$version"
        ln -sf "$HOME/.local/share/claude-$arch/versions/$version" "$bin_dir/claude"
    elif [ -e "$HOME/.local/bin/claude" ]; then
        mv "$HOME/.local/bin/claude" "$bin_dir/claude"
    fi
    rm -f "$HOME/.local/bin/claude"
fi

# uv
if [ "$is_linux" -eq 1 ]; then
    UV_INSTALL_DIR="$bin_dir" curl -LsSf https://astral.sh/uv/install.sh | sh
else
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# rg
if [ $is_linux -eq 1 ]; then

    case "$arch" in
        x86_64)
            RG="ripgrep-14.1.1-x86_64-unknown-linux-musl"
            NVIM="nvim-linux-x86_64"
            DELTA="delta-0.18.2-x86_64-unknown-linux-musl"
            BAT="bat-v0.25.0-x86_64-unknown-linux-musl"
            FD="fd-v10.2.0-x86_64-unknown-linux-musl"
            GH="gh_2.68.1_linux_amd64"
            ;;
        aarch64)
            RG="ripgrep-14.1.1-aarch64-unknown-linux-gnu"
            NVIM="nvim-linux-arm64"
            DELTA="delta-0.18.2-aarch64-unknown-linux-gnu"
            BAT="bat-v0.25.0-aarch64-unknown-linux-musl"
            FD="fd-v10.2.0-aarch64-unknown-linux-musl"
            GH="gh_2.68.1_linux_arm64"
            ;;
        *)
            echo "Unsupported arch: $arch"; exit 1
            ;;
    esac

    cd "$bin_dir"
    curl -LO "https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/${RG}.tar.gz"
    tar -xvzf "${RG}.tar.gz"
    ln -s "${RG}/rg" .

    curl -LO "https://github.com/neovim/neovim/releases/download/v0.11.0/${NVIM}.tar.gz"
    tar -xvzf "${NVIM}.tar.gz"
    ln -s "${NVIM}/bin/nvim" .

    curl -LO "https://github.com/dandavison/delta/releases/download/0.18.2/${DELTA}.tar.gz"
    tar -xvzf "${DELTA}.tar.gz"
    ln -s "${DELTA}/delta" .

    curl -LO "https://github.com/sharkdp/bat/releases/download/v0.25.0/${BAT}.tar.gz"
    tar -xvzf "${BAT}.tar.gz"
    ln -s "${BAT}/bat" .

    curl -LO "https://github.com/sharkdp/fd/releases/download/v10.2.0/${FD}.tar.gz"
    tar -xvzf "${FD}.tar.gz"
    ln -s "${FD}/fd" .

    curl -LO "https://github.com/cli/cli/releases/download/v2.68.1/${GH}.tar.gz"
    tar -xvzf "${GH}.tar.gz"
    ln -s "${GH}/bin/gh" .


    export CARGO_HOME="$HOME/.cargo-$arch"
    export RUSTUP_HOME="$HOME/.rustup-$arch"
    curl https://sh.rustup.rs -sSf | sh -s -- -y --no-modify-path
    source "$CARGO_HOME/env"
    cargo install tree-sitter-cli
    cargo install starship

else
    # Install brew
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install neovim
    brew install ripgrep
    brew install tmux
    brew install fd
    brew install bat
    brew install --cask font-jetbrains-mono-nerd-font
    brew install nodejs
    brew install npm
    brew install luarocks
    brew install git-delta
    brew install --cask nikitabobko/tap/aerospace
    brew install --cask mactex
    brew install pygments
    brew install pyenv
    brew install pyenv-virtualenv
    brew install --cask skim
    brew install gh
    brew install git-lfs
    brew install gnupg
    brew install charmbracelet/tap/freeze
    brew install tree
    brew install openshift-cli 
    brew install mac-mouse-fix
    brew install helm 

fi
