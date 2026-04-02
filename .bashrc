source ~/.commonrc

# History: large size
export HISTSIZE=10000000
export HISTFILESIZE=$HISTSIZE

# History: immediate append + deduplication + verify
shopt -s histappend
PROMPT_COMMAND="history -a;$PROMPT_COMMAND"
HISTCONTROL=ignorespace:erasedups
shopt -s histverify

# FZF
[ -f ~/.fzf.bash ] && source ~/.fzf.bash

# API key loading
API_KEY_DIR=$DOTFILES/API_KEYS
if [ -d "$API_KEY_DIR" ]; then
    for file in "$API_KEY_DIR"/*; do
        stem=$(basename "$file")
        export "$stem=$(cat "$file" | xargs)"
    done
fi

# Key bindings
bind '"\C-g": "tmux-sessionizer\n"'
bind '"\C-f": "tmux-list-sessionizer\n"'
bind '"\C-x\C-e": edit-and-execute-command'

# starship
if command -v starship &> /dev/null
then
    eval "$(starship init bash)"
fi

