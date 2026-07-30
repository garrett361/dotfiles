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
        # typst is only used on macOS, so tinymist is not installed on the Linux arms.
        TINYMIST_ASSET="tinymist-aarch64-apple-darwin.tar.gz"
        CODELLDB_ASSET="codelldb-darwin-arm64.vsix"
        TREE_SITTER="tree-sitter-${TREE_SITTER_VERSION}-macos-arm64"
        TREE_SITTER_ASSET="tree-sitter-macos-arm64.gz"
        STARSHIP="starship-${STARSHIP_VERSION}-aarch64-apple-darwin"
        STARSHIP_ASSET="starship-aarch64-apple-darwin.tar.gz"
        RG="ripgrep-${RG_VERSION}-aarch64-apple-darwin"
        DELTA="delta-${DELTA_VERSION}-aarch64-apple-darwin"
        BAT="bat-v${BAT_VERSION}-aarch64-apple-darwin"
        FD="fd-v${FD_VERSION}-aarch64-apple-darwin"
        CODEX_ASSET="codex-aarch64-apple-darwin.tar.gz"
        ;;
    Linux-x86_64)
        NVIM="nvim-linux-x86_64"
        CLANGD_ASSET="clangd-linux-${CLANGD_VERSION}.zip"
        LUA_LS_ASSET="lua-language-server-${LUA_LS_VERSION}-linux-x64.tar.gz"
        # musl for ruff/ty/stylua: stylua's gnu builds need GLIBC_2.34, which rules out RHEL 8/9,
        # Ubuntu 20.04 and Debian 11.
        RUFF_ASSET="ruff-x86_64-unknown-linux-musl.tar.gz"
        TY_ASSET="ty-x86_64-unknown-linux-musl.tar.gz"
        STYLUA_ASSET="stylua-linux-x86_64-musl.zip"
        CODELLDB_ASSET="codelldb-linux-x64.vsix"
        TREE_SITTER="tree-sitter-${TREE_SITTER_VERSION}-linux-x64"
        TREE_SITTER_ASSET="tree-sitter-linux-x64.gz"
        STARSHIP="starship-${STARSHIP_VERSION}-x86_64-unknown-linux-gnu"
        STARSHIP_ASSET="starship-x86_64-unknown-linux-gnu.tar.gz"
        RG="ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl"
        DELTA="delta-${DELTA_VERSION}-x86_64-unknown-linux-musl"
        BAT="bat-v${BAT_VERSION}-x86_64-unknown-linux-musl"
        FD="fd-v${FD_VERSION}-x86_64-unknown-linux-musl"
        CODEX_ASSET="codex-x86_64-unknown-linux-musl.tar.gz"
        ;;
    Linux-aarch64)
        NVIM="nvim-linux-arm64"
        # No CLANGD_ASSET: upstream ships no aarch64 Linux build (clangd#514 is open since 2020),
        # so these machines get no C/C++ LSP. Mason could not serve them either.
        LUA_LS_ASSET="lua-language-server-${LUA_LS_VERSION}-linux-arm64.tar.gz"
        RUFF_ASSET="ruff-aarch64-unknown-linux-musl.tar.gz"
        TY_ASSET="ty-aarch64-unknown-linux-musl.tar.gz"
        STYLUA_ASSET="stylua-linux-aarch64-musl.zip"
        CODELLDB_ASSET="codelldb-linux-arm64.vsix"
        TREE_SITTER="tree-sitter-${TREE_SITTER_VERSION}-linux-arm64"
        TREE_SITTER_ASSET="tree-sitter-linux-arm64.gz"
        STARSHIP="starship-${STARSHIP_VERSION}-aarch64-unknown-linux-musl"
        STARSHIP_ASSET="starship-aarch64-unknown-linux-musl.tar.gz"
        RG="ripgrep-${RG_VERSION}-aarch64-unknown-linux-gnu"
        DELTA="delta-${DELTA_VERSION}-aarch64-unknown-linux-gnu"
        BAT="bat-v${BAT_VERSION}-aarch64-unknown-linux-musl"
        FD="fd-v${FD_VERSION}-aarch64-unknown-linux-musl"
        CODEX_ASSET="codex-aarch64-unknown-linux-musl.tar.gz"
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
        rm -f "${NVIM}.tar.gz"
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
        rm -f "${STARSHIP_ASSET}"
    fi
    ln -sf "${STARSHIP}/starship" .

    if [ "$force" -eq 1 ] || [ ! -d "${RG}" ]; then
        rm -rf "${RG}"
        curl -LO "https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/${RG}.tar.gz"
        tar -xvzf "${RG}.tar.gz"
        rm -f "${RG}.tar.gz"
    fi
    ln -sf "${RG}/rg" .

    if [ "$force" -eq 1 ] || [ ! -d "${DELTA}" ]; then
        rm -rf "${DELTA}"
        curl -LO "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/${DELTA}.tar.gz"
        tar -xvzf "${DELTA}.tar.gz"
        rm -f "${DELTA}.tar.gz"
    fi
    ln -sf "${DELTA}/delta" .

    if [ "$force" -eq 1 ] || [ ! -d "${BAT}" ]; then
        rm -rf "${BAT}"
        curl -LO "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/${BAT}.tar.gz"
        tar -xvzf "${BAT}.tar.gz"
        rm -f "${BAT}.tar.gz"
    fi
    ln -sf "${BAT}/bat" .

    if [ "$force" -eq 1 ] || [ ! -d "${FD}" ]; then
        rm -rf "${FD}"
        curl -LO "https://github.com/sharkdp/fd/releases/download/v${FD_VERSION}/${FD}.tar.gz"
        tar -xvzf "${FD}.tar.gz"
        rm -f "${FD}.tar.gz"
    fi
    ln -sf "${FD}/fd" .

    # Several tools below ship zips. Collect what gets skipped so one missing prerequisite is
    # reported once at the end rather than scrolling past in the middle of tar output.
    have_unzip=0
    command -v unzip &>/dev/null && have_unzip=1
    skipped=""

    # clangd: pinned here rather than left to mason-lspconfig, and deliberately not brew or Xcode,
    # whose clang lags well behind. The zip already unpacks to a version-stamped dir.
    if [ -n "$CLANGD_ASSET" ]; then
        if [ "$have_unzip" -eq 0 ]; then
            skipped="$skipped clangd"
        else
            clangd_dir="clangd_${CLANGD_VERSION}"
            if [ "$force" -eq 1 ] || [ ! -d "$clangd_dir" ]; then
                # Chained so a bad tag leaves the working copy alone; -o so a --force re-run does
                # not stop at unzip's interactive replace prompt.
                if curl -fLO "https://github.com/clangd/clangd/releases/download/${CLANGD_VERSION}/${CLANGD_ASSET}" \
                    && unzip -q -o "$CLANGD_ASSET" \
                    && [ -x "$clangd_dir/bin/clangd" ]; then
                    find "$bin_dir" -maxdepth 1 -name 'clangd_*' ! -name "$clangd_dir" -exec rm -rf {} +
                else
                    echo "clangd ${CLANGD_VERSION} install failed; keeping existing" >&2
                    skipped="$skipped clangd"
                fi
                rm -f "$CLANGD_ASSET"
            fi
            [ -d "$clangd_dir" ] && ln -sf "$clangd_dir/bin/clangd" .
        fi
    fi

    # ruff, ty and tinymist each ship a tarball holding a single top-level dir named after the
    # target triple, with no version in it. Extracting as-is would make the [ ! -d ] guard true
    # forever and a version bump a silent no-op, so strip the dir and name it ourselves. One
    # helper rather than three near-identical blocks; the rest of this script predates it.
    install_tarball() {
        local name=$1 version=$2 asset=$3 url=$4
        local dir="${name}-${version}"
        if [ "$force" -eq 1 ] || [ ! -d "$dir" ]; then
            rm -rf "$dir.tmp"
            # Chained so a bad tag or a truncated download leaves the working copy in place.
            if curl -fLO "$url" \
                && mkdir -p "$dir.tmp" \
                && tar -xzf "$asset" -C "$dir.tmp" --strip-components=1 \
                && [ -x "$dir.tmp/$name" ]; then
                rm -rf "$dir" && mv "$dir.tmp" "$dir"
                # Prune only once the new version is in place, or this eats what it just installed.
                find "$bin_dir" -maxdepth 1 -name "${name}-*" ! -name "$dir" -exec rm -rf {} +
            else
                echo "$name $version install failed; keeping existing" >&2
                skipped="$skipped $name"
            fi
            rm -rf "$dir.tmp" "$asset"
        fi
        [ -d "$dir" ] && ln -sf "$dir/$name" .
    }

    install_tarball ruff "$RUFF_VERSION" "$RUFF_ASSET" \
        "https://github.com/astral-sh/ruff/releases/download/${RUFF_VERSION}/${RUFF_ASSET}"
    install_tarball ty "$TY_VERSION" "$TY_ASSET" \
        "https://github.com/astral-sh/ty/releases/download/${TY_VERSION}/${TY_ASSET}"
    if [ -n "$TINYMIST_ASSET" ]; then
        install_tarball tinymist "$TINYMIST_VERSION" "$TINYMIST_ASSET" \
            "https://github.com/Myriad-Dreamin/tinymist/releases/download/v${TINYMIST_VERSION}/${TINYMIST_ASSET}"
    fi

    # lua-language-server unpacks flat (bin/, main.lua, locale/, meta/), so it gets its own dir
    # instead of --strip-components, and an absolute one because the wrapper embeds the path.
    lua_ls_dir="$bin_dir/lua-language-server-${LUA_LS_VERSION}"
    if [ "$force" -eq 1 ] || [ ! -d "$lua_ls_dir" ]; then
        rm -rf "$lua_ls_dir.tmp"
        if curl -fLO "https://github.com/LuaLS/lua-language-server/releases/download/${LUA_LS_VERSION}/${LUA_LS_ASSET}" \
            && mkdir -p "$lua_ls_dir.tmp" \
            && tar -xzf "$LUA_LS_ASSET" -C "$lua_ls_dir.tmp" \
            && [ -x "$lua_ls_dir.tmp/bin/lua-language-server" ]; then
            rm -rf "$lua_ls_dir" && mv "$lua_ls_dir.tmp" "$lua_ls_dir"
            find "$bin_dir" -maxdepth 1 -name 'lua-language-server-*' \
                ! -name "$(basename "$lua_ls_dir")" -exec rm -rf {} +
        else
            echo "lua-language-server ${LUA_LS_VERSION} install failed; keeping existing" >&2
            skipped="$skipped lua-language-server"
        fi
        rm -rf "$lua_ls_dir.tmp" "$LUA_LS_ASSET"
    fi
    # A wrapper, not a symlink: it locates main.lua relative to its own executable path, which on
    # macOS is not symlink-resolved. Outside the guard so a deleted wrapper self-heals.
    if [ -x "$lua_ls_dir/bin/lua-language-server" ]; then
        printf '#!/bin/sh\nexec "%s/bin/lua-language-server" "$@"\n' "$lua_ls_dir" > lua-language-server
        chmod +x lua-language-server
    fi

    # stylua ships a bare binary inside a zip, so it needs unzip and a dir of its own.
    if [ "$have_unzip" -eq 0 ]; then
        skipped="$skipped stylua"
    else
        stylua_dir="stylua-${STYLUA_VERSION}"
        if [ "$force" -eq 1 ] || [ ! -d "$stylua_dir" ]; then
            if curl -fLO "https://github.com/JohnnyMorganz/StyLua/releases/download/v${STYLUA_VERSION}/${STYLUA_ASSET}" \
                && unzip -q -o -j "$STYLUA_ASSET" -d "$stylua_dir" \
                && chmod +x "$stylua_dir/stylua"; then
                find "$bin_dir" -maxdepth 1 -name 'stylua-*' ! -name "$stylua_dir" -exec rm -rf {} +
            else
                echo "stylua ${STYLUA_VERSION} install failed; keeping existing" >&2
                skipped="$skipped stylua"
            fi
            rm -f "$STYLUA_ASSET"
        fi
        [ -d "$stylua_dir" ] && ln -sf "$stylua_dir/stylua" .
    fi

    # codelldb: debug adapter for nvim-dap-lldb (c/cpp/rust). Ships as a per-platform vsix (a zip)
    # with no brew formula.
    codelldb_dir="$bin_dir/codelldb-${CODELLDB_VERSION}"
    if [ "$have_unzip" -eq 0 ]; then
        skipped="$skipped codelldb"
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

    # codex: tracks latest rather than a pinned version, like Claude Code above, since both
    # release very frequently. The tarball holds one bare binary named after the target triple.
    if curl -fLO "https://github.com/openai/codex/releases/latest/download/${CODEX_ASSET}"; then
        tar -xzf "${CODEX_ASSET}"
        # Only replace a working codex once the new binary is actually on disk.
        if [ -f "${CODEX_ASSET%.tar.gz}" ]; then
            mv -f "${CODEX_ASSET%.tar.gz}" codex
            chmod +x codex
        fi
        rm -f "${CODEX_ASSET}"
    else
        echo "codex download failed; keeping whatever is already installed" >&2
    fi

    if [ -n "$skipped" ]; then
        echo "Skipped (missing prerequisite or failed download):$skipped" >&2
    fi
fi

# gh is Linux-only here: macOS ships a .zip rather than a tarball, so it stays on brew.
if [ $is_linux -eq 1 ]; then

    GH_VERSION="2.96.0"

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
        rm -f "${GH}.tar.gz"
    fi
    ln -sf "${GH}/bin/gh" .

else
    # Install brew
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install tmux
    brew install --cask font-jetbrains-mono-nerd-font
    brew install nodejs
    brew install luarocks
    brew install --cask nikitabobko/tap/aerospace
    brew install --cask mactex
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
