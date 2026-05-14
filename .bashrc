source ~/.commonrc

# History: large size
export HISTSIZE=10000000
export HISTFILESIZE=$HISTSIZE

# History: immediate append + deduplication + verify
shopt -s histappend
HISTCONTROL=ignorespace:erasedups
shopt -s histverify

# FZF
_fzf_dir="$HOME/.fzf-$(uname -m)"
[[ $- == *i* ]] && [ -f "$_fzf_dir/shell/completion.bash" ] && source "$_fzf_dir/shell/completion.bash"
[ -f "$_fzf_dir/shell/key-bindings.bash" ] && source "$_fzf_dir/shell/key-bindings.bash"
unset _fzf_dir

# Key bindings
bind '"\C-g": "tmux-sessionizer\n"'
bind '"\C-f": "tmux-list-sessionizer\n"'
bind '"\C-x\C-e": edit-and-execute-command'

# starship (guard against arch mismatch in containers)
if command -v starship &>/dev/null && starship --version &>/dev/null; then
    eval "$(starship init bash)"
fi
PROMPT_COMMAND="history -a; history -n; ${PROMPT_COMMAND}"

