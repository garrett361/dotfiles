# Homebrew (macOS only)
[ "$(uname -s)" = "Darwin" ] && [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"

_arch=$(uname -m)

[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin/$_arch:$HOME/.local/bin:$PATH"

if [ -f "$HOME/.cargo-$_arch/env" ]; then
    . "$HOME/.cargo-$_arch/env"
elif [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi

[ "$_arch" = "x86_64" ] && [ -f "$HOME/x86/bin/env" ] && . "$HOME/x86/bin/env"
unset _arch
