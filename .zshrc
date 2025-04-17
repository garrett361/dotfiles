################################   EXPORTS  ################################

# go paths
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin

# script paths
export PATH=$PATH:$HOME/.local/scripts
# In case .local/bin isn't on the path
export PATH=$PATH:$HOME/.local/bin
# nvim, if installed from source
export PATH="$PATH:/opt/nvim-linux64/bin"

# useful local paths
export GITHUB=$HOME/github
export DOTFILES=$GITHUB/garrett361/dotfiles

# default editor
export EDITOR="env PYTHONPATH=$PYTHONPATH:$PWD nvim"
export VISUAL="$EDITOR"

# rg
export RIPGREP_CONFIG_PATH="$HOME/.rg"

# c/c++
export CC=clang
export CXX=clang++


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


################################   ALIAS  ################################

# v is also nvim
alias v="env PYTHONPATH=$PYTHONPATH:$PWD nvim"

# g is git
alias g="git"

# cd into github
alias cdg="cd $GITHUB; pwd"

# cd into github
alias cdgg="cd ${GITHUB}/garrett361; pwd"

# cd into downloads
alias cdd="cd ${HOME}/Downloads; pwd"

# cd into dotfiles
alias cddot="cd ${GITHUB}/garrett361/dotfiles; pwd"

# cd into github notes dir
alias cdn="cd ${GITHUB}/garrett361/notes; pwd"

# cd into jupyter_notebooks
alias cdj="cd ~/jupyter_notebooks; pwd"

# Show hidden files and details
export CLICOLOR=1
export LSCOLORS=ExGxBxDxCxEgEdxbxgxcxd
alias ll="ls -lhA"

# Move to the parent folder.
alias ..="cd ..;pwd"

# Move up two parent folders.
alias ...="cd ../..;pwd"

# Move up three parent folders.
alias ....="cd ../../..;pwd"


# Safer rm -rf
alias rmrf="rm -rfI"

# tmux helpers
alias tls="tmux list-sessions"
alias tks="tmux kill-session -t"

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


# make a directory and cd to it
function mcd()
{
    test -d "$1" || mkdir "$1" && cd "$1"
}

# create a file and all intervening directories
function mkfile()
{
    mkdir -p "$(dirname "$1")" && touch "$1"
}

function ais_login()
{
    # https://console-openshift-console.apps.ais-5.watson.ibm.com/
    oc login -s https://api.ais-5.watson.ibm.com:6443 --insecure-skip-tls-verify=true -u goon -p abc123
}


# For easier cloning
function gc()
{
    local repo=$(basename $(pwd))
    git clone git@github.com:$repo/$1
}
function gc_ibm()
{
    local repo=$(basename $(pwd))
    git clone git@github.ibm.com:$repo/$1
}


function dotfiles_rebase()
{
    cddot && g fa && g r origin/main && cd -
}

################################   OTHER  ################################

# Rust
[ -f ~/.cargo/env ] && source ~/.cargo/env

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
