if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi

_arch=$(uname -m)

[ -d "$HOME/bin" ] && PATH="$HOME/bin:$PATH"
[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin/$_arch:$HOME/.local/bin:$PATH"

export RUSTUP_HOME="$HOME/.rustup-$_arch"
if [ -f "$HOME/.cargo-$_arch/env" ]; then
    . "$HOME/.cargo-$_arch/env"
elif [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi

[ "$_arch" = "x86_64" ] && [ -f "$HOME/x86/bin/env" ] && . "$HOME/x86/bin/env"
unset _arch
