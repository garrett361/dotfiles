source ~/.commonrc

# Shared, immediate history
# https://askubuntu.com/a/115625
shopt -s histappend
PROMPT_COMMAND="history -a;$PROMPT_COMMAND"

# FZF
[ -f ~/.fzf.bash ] && source ~/.fzf.bash


# starship
if command -v starship &> /dev/null
then
    eval "$(starship init bash)"
fi

