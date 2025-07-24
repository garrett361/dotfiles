################################   EXPORTS  ################################
source ~/.commonrc

# # c/c++
# export CC=clang
# export CXX=clang++


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

################################   TOKENS  ################################

API_KEY_DIR=$DOTFILES/API_KEYS
if [ -d "$API_KEY_DIR" ]; then
    for file in "$API_KEY_DIR"/*; do
        stem=$(basename "$file")
        export "$stem=$(cat $file)"
    done
fi


################################   BINDKEYS  ################################

# Easy tmux session creation
bindkey -s ^g "tmux-sessionizer\n"
# For existing sessions
bindkey -s ^f "tmux-list-sessionizer\n"

################################   OPTIONS  ################################

# Immediately append to history, rather than wait for shell exit
# https://stackoverflow.com/questions/842338/how-do-i-tell-zsh-to-write-the-current-shells-history-to-my-history-file
setopt INC_APPEND_HISTORY

################################   FUNCTIONS  ################################


function ais_login()
{
    # https://console-openshift-console.apps.ais-5.watson.ibm.com/
    oc login -s https://api.ais-5.watson.ibm.com:6443 --insecure-skip-tls-verify=true -u goon -p abc123
}


################################   OTHER  ################################

# FZF
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

# pyenv
if command -v pyenv &> /dev/null
then
    export PYENV_ROOT="$HOME/.pyenv"
    [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
fi

# starship
if command -v starship &> /dev/null
then
    eval "$(starship init zsh)"
fi



# # For zsh-syntax-highlighting installed via brew
# source $(brew --prefix)/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
# # For zsh-autosuggestions via brew
# source $(brew --prefix)/share/zsh-autosuggestions/zsh-autosuggestions.zsh
