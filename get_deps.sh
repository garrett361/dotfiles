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
# The wipe is Linux-only. There this path is just staging: the binary is re-homed to
# claude-$arch below and ~/.local/bin/claude is deleted, so clearing it costs nothing and is what
# forces the arch-correct copy (the claude `install` subcommand skips copying when the version
# already exists). On macOS this path is the live install and the symlink on PATH points into it,
# so wiping before the download would leave no claude at all if the download failed.
if [ "$is_linux" -eq 1 ]; then
    rm -f "$HOME/.local/share/claude/versions"/*
fi
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
CLANGD_VERSION="22.1.6"
LUA_LS_VERSION="3.18.2"
RUFF_VERSION="0.16.0"
TY_VERSION="0.0.65"
STYLUA_VERSION="2.5.2"
TINYMIST_VERSION="0.15.2"
CODELLDB_VERSION="1.12.2"
TREE_SITTER_VERSION="0.26.11"
STARSHIP_VERSION="1.26.0"
RG_VERSION="15.2.0"
DELTA_VERSION="0.19.2"
BAT_VERSION="0.26.1"
FD_VERSION="10.4.2"
GH_VERSION="2.96.0"

pinned_ok=1
case "$(uname -s)-$arch" in
    Darwin-arm64)
        NVIM="nvim-macos-arm64"
        # Universal binary, so this one asset also covers Intel macs if an arm is ever added.
        CLANGD_ASSET="clangd-mac-${CLANGD_VERSION}.zip"
        LUA_LS_ASSET="lua-language-server-${LUA_LS_VERSION}-darwin-arm64.tar.gz"
        RUFF_ASSET="ruff-aarch64-apple-darwin.tar.gz"
        TY_ASSET="ty-aarch64-apple-darwin.tar.gz"
        STYLUA_ASSET="stylua-macos-aarch64.zip"
        TINYMIST_ASSET="tinymist-aarch64-apple-darwin.tar.gz"
        CODELLDB_ASSET="codelldb-darwin-arm64.vsix"
        TREE_SITTER_ASSET="tree-sitter-macos-arm64.gz"
        STARSHIP_ASSET="starship-aarch64-apple-darwin.tar.gz"
        RG="ripgrep-${RG_VERSION}-aarch64-apple-darwin"
        DELTA="delta-${DELTA_VERSION}-aarch64-apple-darwin"
        BAT="bat-v${BAT_VERSION}-aarch64-apple-darwin"
        FD="fd-v${FD_VERSION}-aarch64-apple-darwin"
        CODEX_ASSET="codex-aarch64-apple-darwin.tar.gz"
        GH_ASSET="gh_${GH_VERSION}_macOS_arm64.zip"
        ;;
    Linux-x86_64)
        NVIM="nvim-linux-x86_64"
        CLANGD_ASSET="clangd-linux-${CLANGD_VERSION}.zip"
        # LuaLS ships glibc-only builds, so unlike the three below it stays exposed to old distros.
        LUA_LS_ASSET="lua-language-server-${LUA_LS_VERSION}-linux-x64.tar.gz"
        # musl for ruff/ty/stylua: stylua's gnu builds need GLIBC_2.34, which rules out RHEL 8/9,
        # Ubuntu 20.04 and Debian 11.
        RUFF_ASSET="ruff-x86_64-unknown-linux-musl.tar.gz"
        TY_ASSET="ty-x86_64-unknown-linux-musl.tar.gz"
        STYLUA_ASSET="stylua-linux-x86_64-musl.zip"
        # No TINYMIST_ASSET: typst is only used on macOS.
        CODELLDB_ASSET="codelldb-linux-x64.vsix"
        TREE_SITTER_ASSET="tree-sitter-linux-x64.gz"
        STARSHIP_ASSET="starship-x86_64-unknown-linux-gnu.tar.gz"
        RG="ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl"
        DELTA="delta-${DELTA_VERSION}-x86_64-unknown-linux-musl"
        BAT="bat-v${BAT_VERSION}-x86_64-unknown-linux-musl"
        FD="fd-v${FD_VERSION}-x86_64-unknown-linux-musl"
        CODEX_ASSET="codex-x86_64-unknown-linux-musl.tar.gz"
        GH_ASSET="gh_${GH_VERSION}_linux_amd64.tar.gz"
        ;;
    Linux-aarch64)
        NVIM="nvim-linux-arm64"
        # No CLANGD_ASSET: upstream ships no aarch64 Linux build (clangd#514 is open since 2020),
        # so these machines get no C/C++ LSP. Mason could not serve them either.
        LUA_LS_ASSET="lua-language-server-${LUA_LS_VERSION}-linux-arm64.tar.gz"
        RUFF_ASSET="ruff-aarch64-unknown-linux-musl.tar.gz"
        TY_ASSET="ty-aarch64-unknown-linux-musl.tar.gz"
        STYLUA_ASSET="stylua-linux-aarch64-musl.zip"
        # No TINYMIST_ASSET: typst is only used on macOS.
        CODELLDB_ASSET="codelldb-linux-arm64.vsix"
        TREE_SITTER_ASSET="tree-sitter-linux-arm64.gz"
        STARSHIP_ASSET="starship-aarch64-unknown-linux-musl.tar.gz"
        RG="ripgrep-${RG_VERSION}-aarch64-unknown-linux-gnu"
        DELTA="delta-${DELTA_VERSION}-aarch64-unknown-linux-gnu"
        BAT="bat-v${BAT_VERSION}-aarch64-unknown-linux-musl"
        FD="fd-v${FD_VERSION}-aarch64-unknown-linux-musl"
        CODEX_ASSET="codex-aarch64-unknown-linux-musl.tar.gz"
        GH_ASSET="gh_${GH_VERSION}_linux_arm64.tar.gz"
        ;;
    *)
        # Warn rather than exit: fzf, uv, claude and the brew branch still work.
        echo "No pinned binaries for $(uname -s)-$arch; skipping pinned installs" >&2
        pinned_ok=0
        ;;
esac

cd "$bin_dir" || exit 1

have_unzip=0
command -v unzip &>/dev/null && have_unzip=1
skipped=""
# Sweep staging dirs from an interrupted run. Each install clears its own before extracting, but
# only when it enters its version guard, so a leftover would otherwise sit there (368 MB, for
# clangd) until the next version bump. Restore first: a run interrupted mid-swap leaves the previous
# install at <tool>.tmp/old, and sweeping that away before the retry would lose it if the retry
# also failed.
for staged in "$bin_dir"/*.tmp; do
    if [ -d "$staged/old" ] && [ ! -e "${staged%.tmp}" ]; then
        mv "$staged/old" "${staged%.tmp}"
    fi
done
rm -rf "$bin_dir"/*.tmp

# Upstream is inconsistent about wrapping the payload in a top-level dir, and clangd stamps the
# version into that dir's name, so detect it instead of passing a flag. Called in a subshell.
single_dir() {
    set -- "$1"/*
    if [ $# -eq 1 ] && [ -d "$1" ]; then echo "$1"; else echo "${1%/*}"; fi
}

# One installer for every pinned release. Upstream ships several archive shapes but they are all
# "an archive holding one executable", so the only per-tool facts are the URL, where the executable
# sits inside the archive, and whether it needs a wrapper instead of a symlink.
#
#   install_pinned <name> <version> <url> [path-to-exe-inside-archive] [wrapper]
#
# The guard is the executable itself rather than its directory, so any half-finished state (partial
# rm, interrupted extract) is retried by the next ordinary run instead of needing --force.
install_pinned() {
    local name=$1 version=$2 url=$3 exe=${4:-$1} wrapper=${5:-}
    local dir="$name-$version" tmp="$name-$version.tmp" asset="${url##*/}" src
    case "$asset" in
        *.zip | *.vsix)
            if [ "$have_unzip" -eq 0 ]; then
                skipped="$skipped $name"
                return
            fi
            ;;
    esac
    if [ "$force" -eq 1 ] || [ "$version" = latest ] || [ ! -x "$dir/$exe" ]; then
        rm -rf "$tmp"
        # One && chain, including the swap: a failed rm or mv has to reach the else arm, or the
        # prune below would still run and delete what it just staged. The archive downloads inside
        # $tmp so one rm clears it too, and no half-finished tarball is left on PATH. The old copy
        # is renamed aside rather than deleted, so the failure arm can put it back.
        # </dev/null: unzip's write-error prompt must fail rather than hang the script.
        if mkdir -p "$tmp/x" \
            && curl -fL -o "$tmp/$asset" "$url" \
            && case "$asset" in
                *.tar.gz) tar -xzf "$tmp/$asset" -C "$tmp/x" ;;
                *.zip | *.vsix) unzip -q "$tmp/$asset" -d "$tmp/x" </dev/null ;;
                *.gz) gunzip -c "$tmp/$asset" >"$tmp/x/$exe" ;;
                *) echo "$name: unhandled archive type $asset" >&2; false ;;
            esac \
            && src=$(single_dir "$tmp/x") \
            && [ -f "$src/$exe" ] \
            && chmod +x "$src/$exe" \
            && { [ ! -e "$dir" ] || mv "$dir" "$tmp/old"; } \
            && mv "$src" "$dir"; then
            # Prune only once the new version is in place, or this eats what it just installed.
            find "$bin_dir" -maxdepth 1 -name "$name-*" ! -name "$dir" -exec rm -rf {} +
        else
            [ -d "$tmp/old" ] && [ ! -e "$dir" ] && mv "$tmp/old" "$dir"
            echo "$name $version install failed; keeping existing" >&2
            skipped="$skipped $name"
        fi
        rm -rf "$tmp"
    fi
    # Outside the guard, so a deleted symlink or wrapper self-heals.
    if [ -x "$dir/$exe" ]; then
        if [ -n "$wrapper" ]; then
            # A wrapper, not a symlink: lua-language-server and codelldb both locate their runtime
            # relative to their own executable path, which macOS does not symlink-resolve. rm -f
            # first because > follows a symlink and would otherwise overwrite the binary itself.
            rm -f "$name"
            printf '#!/bin/sh\nexec "%s/%s" "$@"\n' "$bin_dir/$dir" "$exe" >"$name" &&
                chmod +x "$name"
        else
            # rm -f for the same reason as the wrapper branch: ln -sf onto a symlink-to-directory
            # creates the link inside it instead of replacing it, and reports success.
            rm -f "$name"
            ln -sf "$dir/$exe" "$name"
        fi
    fi
}

if [ "$pinned_ok" -eq 1 ]; then
    install_pinned nvim "$NVIM_VERSION" \
        "https://github.com/neovim/neovim/releases/download/v${NVIM_VERSION}/${NVIM}.tar.gz" bin/nvim
    install_pinned tree-sitter "$TREE_SITTER_VERSION" \
        "https://github.com/tree-sitter/tree-sitter/releases/download/v${TREE_SITTER_VERSION}/${TREE_SITTER_ASSET}"
    install_pinned starship "$STARSHIP_VERSION" \
        "https://github.com/starship/starship/releases/download/v${STARSHIP_VERSION}/${STARSHIP_ASSET}"
    install_pinned rg "$RG_VERSION" \
        "https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/${RG}.tar.gz"
    install_pinned delta "$DELTA_VERSION" \
        "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/${DELTA}.tar.gz"
    install_pinned bat "$BAT_VERSION" \
        "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/${BAT}.tar.gz"
    install_pinned fd "$FD_VERSION" \
        "https://github.com/sharkdp/fd/releases/download/v${FD_VERSION}/${FD}.tar.gz"

    # clangd is pinned rather than taken from brew or Xcode, whose clang lags well behind. Upstream
    # ships no aarch64 Linux build, so CLANGD_ASSET is unset there and this is skipped; llvm does
    # publish an LLVM-*-Linux-ARM64 tarball if one is ever worth its 1.77 GB.
    if [ -n "$CLANGD_ASSET" ]; then
        install_pinned clangd "$CLANGD_VERSION" \
            "https://github.com/clangd/clangd/releases/download/${CLANGD_VERSION}/${CLANGD_ASSET}" \
            bin/clangd
    fi
    install_pinned ruff "$RUFF_VERSION" \
        "https://github.com/astral-sh/ruff/releases/download/${RUFF_VERSION}/${RUFF_ASSET}"
    install_pinned ty "$TY_VERSION" \
        "https://github.com/astral-sh/ty/releases/download/${TY_VERSION}/${TY_ASSET}"
    if [ -n "$TINYMIST_ASSET" ]; then
        install_pinned tinymist "$TINYMIST_VERSION" \
            "https://github.com/Myriad-Dreamin/tinymist/releases/download/v${TINYMIST_VERSION}/${TINYMIST_ASSET}"
    fi
    install_pinned lua-language-server "$LUA_LS_VERSION" \
        "https://github.com/LuaLS/lua-language-server/releases/download/${LUA_LS_VERSION}/${LUA_LS_ASSET}" \
        bin/lua-language-server wrapper
    install_pinned stylua "$STYLUA_VERSION" \
        "https://github.com/JohnnyMorganz/StyLua/releases/download/v${STYLUA_VERSION}/${STYLUA_ASSET}"
    install_pinned codelldb "$CODELLDB_VERSION" \
        "https://github.com/vadimcn/codelldb/releases/download/v${CODELLDB_VERSION}/${CODELLDB_ASSET}" \
        extension/adapter/codelldb wrapper

    # codex tracks latest rather than a pinned version, like Claude Code above, since both release
    # very frequently. `latest` as the version reinstalls on every run.
    install_pinned codex latest \
        "https://github.com/openai/codex/releases/latest/download/${CODEX_ASSET}" "${CODEX_ASSET%.tar.gz}"

    install_pinned gh "$GH_VERSION" \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${GH_ASSET}" bin/gh

fi

if [ "$is_linux" -eq 0 ]; then
    # Install brew
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install tmux
    brew install --cask font-jetbrains-mono-nerd-font
    brew install nodejs
    brew install luarocks
    brew install --cask nikitabobko/tap/aerospace
    brew install --cask mactex
    brew install --cask skim
    brew install git-lfs
    brew install gnupg
    brew install charmbracelet/tap/freeze
    brew install tree
    brew install openshift-cli 
    brew install mac-mouse-fix
    brew install helm 
fi

# Reported once here rather than per tool, so a missing prerequisite or a failed download is not
# lost in the middle of the output above. Placed after the gh block so it covers that too.
if [ -n "$skipped" ]; then
    echo "Skipped (missing prerequisite or failed download):$skipped" >&2
fi
