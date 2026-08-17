# Homebrew (macOS only)
[ "$(uname -s)" = "Darwin" ] && [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"

# ssh agent: 1password on macos, a forwarded agent on remote hosts. `ssh` itself takes whichever agent
# `IdentityAgent` in ~/.ssh/config names, which per ssh_config(5) overrides this variable; everything
# else (ssh-add, anything not reading that file) has only this variable to go on. Skipped for inbound
# ssh sessions so they keep their own agent rather than this machine's vault.
_op_sock="$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
if [ -z "$SSH_CONNECTION" ] && [ -S "$_op_sock" ]; then
    export SSH_AUTH_SOCK="$_op_sock"
elif [ -S "$HOME/.ssh/agent.sock" ]; then
    # ~/.ssh/rc keeps that stable name on the live forwarded socket. Preferring it over the
    # per-session path sshd hands us is what lets a tmux pane outlive the session that started it.
    export SSH_AUTH_SOCK="$HOME/.ssh/agent.sock"
fi
unset _op_sock

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
