################################   EXPORTS  ################################
source ~/.commonrc

# Enable programmable completions (git, ssh, etc.)
autoload -Uz compinit && compinit

################################   LARGE/SHARED HISTORY  ################################
# https://unix.stackexchange.com/a/273863
export HISTFILE="$HOME/.zsh_history"
export HISTSIZE=10000000
export SAVEHIST=$HISTSIZE
setopt EXTENDED_HISTORY          # Write the history file in the ":start:elapsed;command" format.
setopt INC_APPEND_HISTORY        # Write to the history file immediately, not when the shell exits.
setopt SHARE_HISTORY             # Share history between all sessions.
setopt HIST_EXPIRE_DUPS_FIRST    # Expire duplicate entries first when trimming history.
setopt HIST_IGNORE_ALL_DUPS      # Delete old recorded entry if new entry is a duplicate.
setopt HIST_FIND_NO_DUPS         # Do not display a line previously found.
setopt HIST_IGNORE_SPACE         # Don't record an entry starting with a space.
setopt HIST_SAVE_NO_DUPS         # Don't write duplicate entries in the history file.
setopt HIST_REDUCE_BLANKS        # Remove superfluous blanks before recording entry.
setopt HIST_VERIFY               # Don't execute immediately upon history expansion.
setopt HIST_BEEP                 # Beep when accessing nonexistent history.

################################   BINDKEYS  ################################

# Easy tmux session creation
bindkey -s ^g "tmux-sessionizer\n"
# For existing sessions
bindkey -s ^f "tmux-list-sessionizer\n"

autoload -z edit-command-line
zle -N edit-command-line
bindkey "^X^E" edit-command-line

################################   OPTIONS  ################################

################################   OTHER  ################################

# FZF
_fzf_dir="$HOME/.fzf-$(uname -m)"
[[ $- == *i* ]] && [ -f "$_fzf_dir/shell/completion.zsh" ] && source "$_fzf_dir/shell/completion.zsh"
[ -f "$_fzf_dir/shell/key-bindings.zsh" ] && source "$_fzf_dir/shell/key-bindings.zsh"
unset _fzf_dir

# starship (guard against arch mismatch in containers)
if command -v starship &>/dev/null && starship --version &>/dev/null; then
    eval "$(starship init zsh)"
fi


# git-tree completions
command -v git-tree &>/dev/null && eval "$(git-tree completions zsh)"
