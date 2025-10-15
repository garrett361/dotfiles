#!/bin/bash

is_linux=$(uname -s | grep -iq linux && echo 1 || echo 0)

# Create the .local/bin dir if it doesn't exist
bin_dir=$HOME/.local/bin

if [ ! -d $bin_dir ]; then
    mkdir -p $bin_dir
fi


# fzf
git clone --depth 1 https://github.com/junegunn/fzf.git ~/.fzf
~/.fzf/install

# rg
if [ $is_linux -eq 1 ]; then

    cd $bin_dir
    RG="ripgrep-14.1.1-x86_64-unknown-linux-musl"
    curl -LO "https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/${RG}.tar.gz"
    tar -xvzf "${RG}.tar.gz"
    ln -s "${RG}/rg" .

    NVIM=nvim-linux-x86_64
    curl -LO https://github.com/neovim/neovim/releases/11.0/download/${NVIM}.tar.gz
    tar -xvzf "${NVIM}.tar.gz"
    ln -s "${NVIM}/bin/nvim" .

    DELTA=delta-0.18.2-x86_64-unknown-linux-musl
    curl -LO "https://github.com/dandavison/delta/releases/download/0.18.2/${DELTA}.tar.gz"
    tar -xvzf "${DELTA}.tar.gz"
    ln -s "${DELTA}/delta" .

    BAT=bat-v0.25.0-x86_64-unknown-linux-musl
    curl -LO "https://github.com/sharkdp/bat/releases/download/v0.25.0/${BAT}.tar.gz"
    tar -xvzf "${BAT}.tar.gz"
    ln -s "${BAT}/bat" .

    FD=fd-v10.2.0-x86_64-unknown-linux-musl
    curl -LO "https://github.com/sharkdp/fd/releases/download/v10.2.0/${FD}.tar.gz"
    tar -xvzf "${FD}.tar.gz"
    ln -s "${FD}/fd" .

    GH=gh_2.68.1_linux_386
    curl -LO "https://github.com/cli/cli/releases/download/v2.68.1/${GH}.tar.gz"
    tar -xvzf "${GH}.tar.gz"
    ln -s "${GH}/bin/gh" .

    curl https://sh.rustup.rs -sSf | sh -s -- -y
    source $HOME/.cargo/env
    # cargo installs
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
