################################   EXPORTS  ################################
source ~/.commonrc

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
        export "$stem=$(cat $file | xargs)"
    done
fi


################################   BINDKEYS  ################################

# Easy tmux session creation
bindkey -s ^g "tmux-sessionizer\n"
# For existing sessions
bindkey -s ^f "tmux-list-sessionizer\n"

autoload -z edit-command-line
zle -N edit-command-line
bindkey "^X^E" edit-command-line

################################   OPTIONS  ################################

# Immediately append to history, rather than wait for shell exit
# https://stackoverflow.com/questions/842338/how-do-i-tell-zsh-to-write-the-current-shells-history-to-my-history-file
setopt INC_APPEND_HISTORY

function _lsf_jobs()
{
    local user_filter=""
    local multi_flag=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --multi)
                multi_flag="-m --bind ctrl-a:select-all"
                shift
                ;;
            *)
                user_filter="$1"
                shift
                ;;
        esac
    done

    user_filter="${user_filter:-goon}"

    local header="JOBID JOB_NAME USER STAT QUEUE EXEC_HOST SUBMIT_TIME GPU_NUM"
    local selected=$(bjobs -o "jobid job_name user stat queue exec_host submit_time gpu_num" \
        | rg "$user_filter" \
        | fzf $multi_flag --header="$header")

    if [[ -n "$selected" ]]; then
        echo "$selected" | awk '{print $1}'
    fi
}

function lsf_info()
{
    local jobid=$(_lsf_jobs "$@")
    if [[ -n "$jobid" ]]; then
        bjobs -l "$jobid"
    fi
}

function lsf_logs()
{
    if [[ -z $TMUX ]]; then
        echo "lsf_logs requires a tmux session"
        return 1
    fi

    local jobid=$(_lsf_jobs "$@")
    [[ -z "$jobid" ]] && return 0

    local job_info=$(bjobs -l "$jobid")

    local stdout_path=$(echo "$job_info" | grep -oP 'Output File <\K[^,>]+')
    local stderr_path=$(echo "$job_info" | grep -oP 'Error File <\K[^,>]+')

    if [[ -z "$stdout_path" && -z "$stderr_path" ]]; then
        echo "Could not extract log file paths from job info"
        return 1
    fi

    if [[ "$stdout_path" == "$stderr_path" ]] || [[ -z "$stderr_path" ]]; then
        if [[ ! -f "$stdout_path" ]]; then
            echo "Log file does not exist yet: $stdout_path"
            return 1
        fi
        tail -f "$stdout_path"
    else
        local stdout_exists=false
        local stderr_exists=false
        [[ -f "$stdout_path" ]] && stdout_exists=true
        [[ -f "$stderr_path" ]] && stderr_exists=true

        if ! $stdout_exists && ! $stderr_exists; then
            echo "Log files do not exist yet:"
            echo "  stdout: $stdout_path"
            echo "  stderr: $stderr_path"
            return 1
        fi

        if $stdout_exists && $stderr_exists; then
            tmux split-window -h "tail -f \"$stderr_path\""
            tail -f "$stdout_path"
        elif $stdout_exists; then
            tail -f "$stdout_path"
        else
            tail -f "$stderr_path"
        fi
    fi
}

function lsf_attach()
{
    local jobid=$(_lsf_jobs "$@")
    [[ -z "$jobid" ]] && return 0
    battach -L $SHELL "$jobid"
}

function lsf_kill()
{
    local jobs=($(_lsf_jobs "$@" --multi))

    [[ ${#jobs[@]} -eq 0 ]] && return 0

    echo "Delete these jobs? [y/N]"
    for job in "${jobs[@]}"; do
        echo "  $job"
    done

    read response
    case "$response" in
        [yY][eE][sS]|[yY])
            DELETE=1
            ;;
        *)
            DELETE=0
            ;;
    esac

    if [[ $DELETE -eq 1 ]]; then
        for job in "${jobs[@]}"; do
            bkill "$job"
            echo "Killing ${job}"
        done
    else
        echo "Delete aborted!"
    fi
}

function lsf_alloc()
{
    local ngpu=${1:-"1"}
    if [ $ngpu -lt 8 ]; then
        bsub -Is -q preemptable -G grp_preemptable -gpu "num=${ngpu}:j_exclusive=yes" -R "rusage[mem=$((225*ngpu))GB]" $SHELL
    else
        bsub -Is -q preemptable -G grp_preemptable -gpu "num=${ngpu}:j_exclusive=yes" -R "rusage[mem=1800GB]" $SHELL
    fi
}

function lsf_jupyterlab()
{
    bsub -I -gpu "num=1:j_exclusive=yes" jupyter-lab --no-browser --port=${1:-"8880"}
}

################################   OTHER  ################################

# FZF
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

# starship
if command -v starship &> /dev/null
then
    eval "$(starship init zsh)"
fi
