[ -d "$HOME/bin" ] && PATH="$HOME/bin:$PATH"
[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin/$(uname -m):$HOME/.local/bin:$PATH"

. "$HOME/.commonprofile"

# .bashrc must source last: its starship guard checks PATH, which needs the
# ~/.local/bin prepends above to already be in place.
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi
