# Homebrew (macOS only)
[ "$(uname -s)" = "Darwin" ] && [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"

_arch=$(uname -m)

[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin/$_arch:$HOME/.local/bin:$PATH"

export RUSTUP_HOME="$HOME/.rustup-$_arch"
# CARGO_HOME has to name whichever tree actually exists. rustup's env file only prepends bin/ to
# PATH, it never exports CARGO_HOME, so leaving it unset sends `cargo install` to ~/.cargo while
# PATH points at the arch-suffixed tree, and the new binary lands somewhere PATH cannot see.
if [ -f "$HOME/.cargo-$_arch/env" ]; then
    export CARGO_HOME="$HOME/.cargo-$_arch"
    . "$HOME/.cargo-$_arch/env"
elif [ -f "$HOME/.cargo/env" ]; then
    export CARGO_HOME="$HOME/.cargo"
    . "$HOME/.cargo/env"
fi

[ "$_arch" = "x86_64" ] && [ -f "$HOME/x86/bin/env" ] && . "$HOME/x86/bin/env"
unset _arch
