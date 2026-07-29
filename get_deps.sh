#!/bin/bash

is_linux=$(uname -s | grep -iq linux && echo 1 || echo 0)
arch=$(uname -m)

force=0
for arg in "$@"; do
    case "$arg" in
        -f|--force) force=1 ;;
    esac
done

# git_tree: cascading-rebase CLI, its own repo cloned parallel to dotfiles.
# Clone only if missing — never rm -rf (it's an active dev checkout).
gt_dir="$(cd "$(dirname "$0")/.." && pwd)/git_tree"
[ -d "$gt_dir/.git" ] || git clone git@github.com:garrett361/git_tree.git "$gt_dir"

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

# Rust toolchain. RUSTUP_HOME has to be set here rather than inherited: .commonrc exports it,
# but get_deps.sh runs before install.sh has symlinked .commonrc into $HOME, so on a fresh
# machine the toolchain would land in ~/.rustup while every later shell looks in
# ~/.rustup-$arch and reports "no default toolchain".
export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup-$arch}"
if ! command -v rustup &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # The installer only edits shell profiles, so source its env to use rustup below.
    . "${CARGO_HOME:-$HOME/.cargo}/env"
fi
rustup default stable
# rustfmt is in the default profile but not --profile minimal, and conform runs it directly.
rustup component add rust-analyzer clippy rustfmt

# Pinned binaries installed identically on macOS and Linux, so the two can't drift. brew is
# reserved for GUI apps and tools with no Linux counterpart here.
NVIM_VERSION="0.12.4"
CODELLDB_VERSION="1.12.2"
TREE_SITTER_VERSION="0.25.10"
STARSHIP_VERSION="1.25.0"
RG_VERSION="14.1.1"
DELTA_VERSION="0.18.2"
BAT_VERSION="0.25.0"
FD_VERSION="10.2.0"

pinned_ok=1
case "$(uname -s)-$arch" in
    Darwin-arm64)
        NVIM="nvim-macos-arm64"
        CODELLDB_ASSET="codelldb-darwin-arm64.vsix"
        TREE_SITTER="tree-sitter-${TREE_SITTER_VERSION}-macos-arm64"
        TREE_SITTER_ASSET="tree-sitter-macos-arm64.gz"
        STARSHIP="starship-${STARSHIP_VERSION}-aarch64-apple-darwin"
        STARSHIP_ASSET="starship-aarch64-apple-darwin.tar.gz"
        RG="ripgrep-${RG_VERSION}-aarch64-apple-darwin"
        DELTA="delta-${DELTA_VERSION}-aarch64-apple-darwin"
        BAT="bat-v${BAT_VERSION}-aarch64-apple-darwin"
        FD="fd-v${FD_VERSION}-aarch64-apple-darwin"
        ;;
    Linux-x86_64)
        NVIM="nvim-linux-x86_64"
        CODELLDB_ASSET="codelldb-linux-x64.vsix"
        TREE_SITTER="tree-sitter-${TREE_SITTER_VERSION}-linux-x64"
        TREE_SITTER_ASSET="tree-sitter-linux-x64.gz"
        STARSHIP="starship-${STARSHIP_VERSION}-x86_64-unknown-linux-gnu"
        STARSHIP_ASSET="starship-x86_64-unknown-linux-gnu.tar.gz"
        RG="ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl"
        DELTA="delta-${DELTA_VERSION}-x86_64-unknown-linux-musl"
        BAT="bat-v${BAT_VERSION}-x86_64-unknown-linux-musl"
        FD="fd-v${FD_VERSION}-x86_64-unknown-linux-musl"
        ;;
    Linux-aarch64)
        NVIM="nvim-linux-arm64"
        CODELLDB_ASSET="codelldb-linux-arm64.vsix"
        TREE_SITTER="tree-sitter-${TREE_SITTER_VERSION}-linux-arm64"
        TREE_SITTER_ASSET="tree-sitter-linux-arm64.gz"
        STARSHIP="starship-${STARSHIP_VERSION}-aarch64-unknown-linux-musl"
        STARSHIP_ASSET="starship-aarch64-unknown-linux-musl.tar.gz"
        RG="ripgrep-${RG_VERSION}-aarch64-unknown-linux-gnu"
        DELTA="delta-${DELTA_VERSION}-aarch64-unknown-linux-gnu"
        BAT="bat-v${BAT_VERSION}-aarch64-unknown-linux-musl"
        FD="fd-v${FD_VERSION}-aarch64-unknown-linux-musl"
        ;;
    *)
        # Warn rather than exit: fzf, uv, claude and the brew branch still work.
        echo "No pinned binaries for $(uname -s)-$arch; skipping pinned installs" >&2
        pinned_ok=0
        ;;
esac

cd "$bin_dir" || exit 1

if [ "$pinned_ok" -eq 1 ]; then
    # The tarball always unpacks to a version-less dir, so rename it to a versioned one. Left
    # as-is, the guard would never re-trigger on a version bump, and tar would overlay the new
    # release onto stale runtime files from the old one.
    if [ "$force" -eq 1 ] || [ ! -d "${NVIM}-${NVIM_VERSION}" ]; then
        rm -rf "${NVIM}" "${NVIM}-${NVIM_VERSION}"
        curl -LO "https://github.com/neovim/neovim/releases/download/v${NVIM_VERSION}/${NVIM}.tar.gz"
        tar -xvzf "${NVIM}.tar.gz"
        mv "${NVIM}" "${NVIM}-${NVIM_VERSION}"
    fi
    ln -sf "${NVIM}-${NVIM_VERSION}/bin/nvim" .

    # tree-sitter ships as a single gzipped binary, not a tarball
    if [ "$force" -eq 1 ] || [ ! -f "${TREE_SITTER}" ]; then
        rm -f "${TREE_SITTER}" "${TREE_SITTER_ASSET}"
        curl -LO "https://github.com/tree-sitter/tree-sitter/releases/download/v${TREE_SITTER_VERSION}/${TREE_SITTER_ASSET}"
        gunzip -f "${TREE_SITTER_ASSET}"
        mv "${TREE_SITTER_ASSET%.gz}" "${TREE_SITTER}"
        chmod +x "${TREE_SITTER}"
    fi
    ln -sf "${TREE_SITTER}" tree-sitter

    # starship tarball contains a bare `starship` binary, so extract into a versioned dir
    if [ "$force" -eq 1 ] || [ ! -d "${STARSHIP}" ]; then
        rm -rf "${STARSHIP}"
        curl -LO "https://github.com/starship/starship/releases/download/v${STARSHIP_VERSION}/${STARSHIP_ASSET}"
        mkdir -p "${STARSHIP}"
        tar -xzf "${STARSHIP_ASSET}" -C "${STARSHIP}"
    fi
    ln -sf "${STARSHIP}/starship" .

    if [ "$force" -eq 1 ] || [ ! -d "${RG}" ]; then
        rm -rf "${RG}"
        curl -LO "https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/${RG}.tar.gz"
        tar -xvzf "${RG}.tar.gz"
    fi
    ln -sf "${RG}/rg" .

    if [ "$force" -eq 1 ] || [ ! -d "${DELTA}" ]; then
        rm -rf "${DELTA}"
        curl -LO "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/${DELTA}.tar.gz"
        tar -xvzf "${DELTA}.tar.gz"
    fi
    ln -sf "${DELTA}/delta" .

    if [ "$force" -eq 1 ] || [ ! -d "${BAT}" ]; then
        rm -rf "${BAT}"
        curl -LO "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/${BAT}.tar.gz"
        tar -xvzf "${BAT}.tar.gz"
    fi
    ln -sf "${BAT}/bat" .

    if [ "$force" -eq 1 ] || [ ! -d "${FD}" ]; then
        rm -rf "${FD}"
        curl -LO "https://github.com/sharkdp/fd/releases/download/v${FD_VERSION}/${FD}.tar.gz"
        tar -xvzf "${FD}.tar.gz"
    fi
    ln -sf "${FD}/fd" .

    # codelldb: debug adapter for nvim-dap-lldb (c/cpp/rust). Ships as a per-platform vsix
    # (a zip) with no brew formula, hence the only unzip dependency in this script.
    codelldb_dir="$bin_dir/codelldb-${CODELLDB_VERSION}"
    if ! command -v unzip &>/dev/null; then
        echo "unzip not found; skipping codelldb (c/cpp/rust debugging)" >&2
    else
        if [ "$force" -eq 1 ] || [ ! -d "$codelldb_dir" ]; then
            rm -rf "$codelldb_dir"
            curl -fLo "$CODELLDB_ASSET" "https://github.com/vadimcn/codelldb/releases/download/v${CODELLDB_VERSION}/${CODELLDB_ASSET}"
            unzip -q "$CODELLDB_ASSET" -d "$codelldb_dir"
            rm -f "$CODELLDB_ASSET"
        fi
        # A wrapper, not a symlink: codelldb locates liblldb relative to current_exe(), which
        # on macOS does not resolve symlinks. Written outside the guard so a deleted wrapper
        # self-heals, and with a single-quoted format so "$@" survives into the file.
        if [ -x "$codelldb_dir/extension/adapter/codelldb" ]; then
            printf '#!/bin/sh\nexec "%s/extension/adapter/codelldb" "$@"\n' "$codelldb_dir" > codelldb
            chmod +x codelldb
        fi
    fi
fi

# gh is Linux-only here: macOS ships a .zip rather than a tarball, so it stays on brew.
if [ $is_linux -eq 1 ]; then

    GH_VERSION="2.68.1"

    case "$arch" in
        x86_64)
            GH="gh_${GH_VERSION}_linux_amd64"
            ;;
        aarch64)
            GH="gh_${GH_VERSION}_linux_arm64"
            ;;
        *)
            echo "Unsupported arch: $arch"; exit 1
            ;;
    esac

    if [ "$force" -eq 1 ] || [ ! -d "${GH}" ]; then
        rm -rf "${GH}"
        curl -LO "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${GH}.tar.gz"
        tar -xvzf "${GH}.tar.gz"
    fi
    ln -sf "${GH}/bin/gh" .

else
    # Install brew
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install tmux
    brew install --cask font-jetbrains-mono-nerd-font
    brew install nodejs
    brew install npm
    brew install luarocks
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
