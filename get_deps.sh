#!/bin/bash

is_linux=$(uname -s | grep -iq linux && echo 1 || echo 0)
arch=$(uname -m)

force=0
for arg in "$@"; do
    case "$arg" in
        -f|--force) force=1 ;;
    esac
done

git -C "$(cd "$(dirname "$0")" && pwd)" submodule update --init

# Arch-specific bin dir so x86 and ARM installs don't collide on a shared home
bin_dir=$HOME/.local/bin/$arch

if [ ! -d $bin_dir ]; then
    mkdir -p $bin_dir
fi


# fzf: clone to arch-specific dir; --bin skips generating ~/.fzf.bash/zsh (we source directly)
if [ "$force" -eq 1 ] || [ ! -d "$HOME/.fzf-$arch" ]; then
    rm -rf "$HOME/.fzf-$arch"
    git clone --depth 1 https://github.com/junegunn/fzf.git "$HOME/.fzf-$arch"
fi
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
            TREE_SITTER="tree-sitter-0.26.8-linux-x64"
            TREE_SITTER_ASSET="tree-sitter-linux-x64.gz"
            STARSHIP="starship-1.25.0-x86_64-unknown-linux-gnu"
            STARSHIP_ASSET="starship-x86_64-unknown-linux-gnu.tar.gz"
            ;;
        aarch64)
            RG="ripgrep-14.1.1-aarch64-unknown-linux-gnu"
            NVIM="nvim-linux-arm64"
            DELTA="delta-0.18.2-aarch64-unknown-linux-gnu"
            BAT="bat-v0.25.0-aarch64-unknown-linux-musl"
            FD="fd-v10.2.0-aarch64-unknown-linux-musl"
            GH="gh_2.68.1_linux_arm64"
            TREE_SITTER="tree-sitter-0.26.8-linux-arm64"
            TREE_SITTER_ASSET="tree-sitter-linux-arm64.gz"
            STARSHIP="starship-1.25.0-aarch64-unknown-linux-musl"
            STARSHIP_ASSET="starship-aarch64-unknown-linux-musl.tar.gz"
            ;;
        *)
            echo "Unsupported arch: $arch"; exit 1
            ;;
    esac

    cd "$bin_dir"
    if [ "$force" -eq 1 ] || [ ! -d "${RG}" ]; then
        rm -rf "${RG}"
        curl -LO "https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/${RG}.tar.gz"
        tar -xvzf "${RG}.tar.gz"
    fi
    ln -sf "${RG}/rg" .

    if [ "$force" -eq 1 ] || [ ! -d "${NVIM}" ]; then
        rm -rf "${NVIM}"
        curl -LO "https://github.com/neovim/neovim/releases/download/v0.11.0/${NVIM}.tar.gz"
        tar -xvzf "${NVIM}.tar.gz"
    fi
    ln -sf "${NVIM}/bin/nvim" .

    if [ "$force" -eq 1 ] || [ ! -d "${DELTA}" ]; then
        rm -rf "${DELTA}"
        curl -LO "https://github.com/dandavison/delta/releases/download/0.18.2/${DELTA}.tar.gz"
        tar -xvzf "${DELTA}.tar.gz"
    fi
    ln -sf "${DELTA}/delta" .

    if [ "$force" -eq 1 ] || [ ! -d "${BAT}" ]; then
        rm -rf "${BAT}"
        curl -LO "https://github.com/sharkdp/bat/releases/download/v0.25.0/${BAT}.tar.gz"
        tar -xvzf "${BAT}.tar.gz"
    fi
    ln -sf "${BAT}/bat" .

    if [ "$force" -eq 1 ] || [ ! -d "${FD}" ]; then
        rm -rf "${FD}"
        curl -LO "https://github.com/sharkdp/fd/releases/download/v10.2.0/${FD}.tar.gz"
        tar -xvzf "${FD}.tar.gz"
    fi
    ln -sf "${FD}/fd" .

    if [ "$force" -eq 1 ] || [ ! -d "${GH}" ]; then
        rm -rf "${GH}"
        curl -LO "https://github.com/cli/cli/releases/download/v2.68.1/${GH}.tar.gz"
        tar -xvzf "${GH}.tar.gz"
    fi
    ln -sf "${GH}/bin/gh" .

    # tree-sitter ships as a single gzipped binary, not a tarball
    if [ "$force" -eq 1 ] || [ ! -f "${TREE_SITTER}" ]; then
        rm -f "${TREE_SITTER}" "${TREE_SITTER_ASSET}"
        curl -LO "https://github.com/tree-sitter/tree-sitter/releases/download/v0.26.8/${TREE_SITTER_ASSET}"
        gunzip -f "${TREE_SITTER_ASSET}"
        mv "${TREE_SITTER_ASSET%.gz}" "${TREE_SITTER}"
        chmod +x "${TREE_SITTER}"
    fi
    ln -sf "${TREE_SITTER}" tree-sitter

    # starship tarball contains a bare `starship` binary, so extract into a versioned dir
    if [ "$force" -eq 1 ] || [ ! -d "${STARSHIP}" ]; then
        rm -rf "${STARSHIP}"
        curl -LO "https://github.com/starship/starship/releases/download/v1.25.0/${STARSHIP_ASSET}"
        mkdir -p "${STARSHIP}"
        tar -xzf "${STARSHIP_ASSET}" -C "${STARSHIP}"
    fi
    ln -sf "${STARSHIP}/starship" .

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
