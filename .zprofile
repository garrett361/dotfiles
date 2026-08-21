# Homebrew (macOS only)
[ "$(uname -s)" = "Darwin" ] && [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"

[ -d "$HOME/.local/bin" ] && PATH="$HOME/.local/bin/$(uname -m):$HOME/.local/bin:$PATH"

. "$HOME/.commonprofile"
