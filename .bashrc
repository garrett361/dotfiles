source ~/.commonrc

# Shared, immediate history
# https://askubuntu.com/a/115625
shopt -s histappend
PROMPT_COMMAND="history -a;$PROMPT_COMMAND"
