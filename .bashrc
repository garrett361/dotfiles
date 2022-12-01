# A minimal bashrc

# g is git
alias g="git"
alias v="vim"
alias sq="squeue"
alias sc="scancel"
alias sa="salloc"

export PATH=$PATH:$HOME/.local/bin
export PATH=$PATH:$HOME/.local/scripts

export GITHUB=$HOME/github
export DOTFILES=$GITHUB/garrett361/dotfiles

# Shared, immediate history
# https://askubuntu.com/a/115625
shopt -s histappend
PROMPT_COMMAND="history -a;$PROMPT_COMMAND"

# Show hidden files and details
alias ll="ls -lhA"

# Move to the parent folder.
alias ..="cd ..;pwd"

# Move up two parent folders.
alias ...="cd ../..;pwd"

# Move up three parent folders.
alias ....="cd ../../..;pwd"


# Safer rm -rf
alias rmrf="rm -rfI"

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

function dotfiles_rebase()
{
    cddot && g fa && g r origin/main && cd -
}

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
