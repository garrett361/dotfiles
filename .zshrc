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
    local query=""
    local fzf_opts=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --multi)
                fzf_opts+=(-m --bind ctrl-a:select-all)
                shift
                ;;
            *)
                if [[ -z "$user_filter" ]]; then
                    user_filter="$1"
                else
                    query="$1"
                fi
                shift
                ;;
        esac
    done

    user_filter="${user_filter:-goon}"

    local header="JOBID JOB_NAME USER STAT QUEUE EXEC_HOST SUBMIT_TIME GPU_NUM"
    local selected=$(bjobs -o "jobid job_name user stat queue exec_host submit_time gpu_num" \
        | rg "$user_filter" \
        | { [[ -n "$query" ]] && rg "$query" || cat; } \
        | fzf "${fzf_opts[@]}" --header="$header")

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


# Helper: open selected log files in tmux panes
function _lsf_open_logs_in_panes()
{
    local log_dir="$1"
    local selected_files="$2"

    if [[ -z "$selected_files" ]]; then
        return 0
    fi

    # Convert to array
    local files=("${(@f)selected_files}")
    local count=${#files[@]}

    # Limit to 4 selections
    if [[ $count -gt 4 ]]; then
        echo "Maximum 4 files supported. Selected: $count"
        return 1
    fi

    # Full paths
    local full_paths=()
    for file in "${files[@]}"; do
        full_paths+=("$log_dir/$file")
    done

    case $count in
        1)
            # Single file: just tail in current pane
            tail -n +1 -f "${full_paths[1]}"
            ;;
        2)
            # Two files: vertical split (side-by-side)
            tmux split-window -h "tail -n +1 -f \"${full_paths[2]}\""
            tail -n +1 -f "${full_paths[1]}"
            ;;
        3)
            # Three files: left full, right split into two
            tmux split-window -h "tail -n +1 -f \"${full_paths[2]}\""
            tmux split-window -v "tail -n +1 -f \"${full_paths[3]}\""
            tail -n +1 -f "${full_paths[1]}"
            ;;
        4)
            # Four files: 2x2 grid (four quadrants)
            tmux split-window -h "tail -n +1 -f \"${full_paths[2]}\""
            tmux select-pane -L
            tmux split-window -v "tail -n +1 -f \"${full_paths[3]}\""
            tmux select-pane -R
            tmux split-window -v "tail -n +1 -f \"${full_paths[4]}\""
            tail -n +1 -f "${full_paths[1]}"
            ;;
    esac
}

function lsf_logs()
{
    if [[ -z $TMUX ]]; then
        echo "lsf_logs requires a tmux session"
        return 1
    fi

    local query=""
    if [[ $# -gt 0 ]]; then
        query="$1"
        shift
    fi

    local jobid=$(_lsf_jobs "$@")
    [[ -z "$jobid" ]] && return 0

    # Get LOG_DIR from bjobs output or $LOG_DIR env var
    local job_json=$(bjobs -o "output_file" -json "$jobid" 2>/dev/null)
    local output_file=$(echo "$job_json" | jq -r '.RECORDS[0].OUTPUT_FILE // empty')

    if [[ -z "$output_file" ]]; then
        echo "Could not determine log directory for job $jobid"
        return 1
    fi

    local log_dir="${LOG_DIR:-$(dirname "$output_file")}"

    if [[ ! -d "$log_dir" ]]; then
        echo "Log directory does not exist: $log_dir"
        return 1
    fi

    # Find all log files matching jobid pattern (single find call)
    # Note: fzf returns selections in list order (top-to-bottom), not tab-selection order
    local selected_files=$(cd "$log_dir" && find . -maxdepth 1 \( \
        -name "*_${jobid}.out" -o \
        -name "*_${jobid}.err" -o \
        -name "*_${jobid}.log" -o \
        -name "*_${jobid}_*.log" \
    \) 2>/dev/null | sed 's|^\./||' | sort \
        | { [[ -n "$query" ]] && rg "$query" || cat; } \
        | fzf -m --bind ctrl-a:select-all \
        --header="Select log files for job $jobid (Tab=multi-select, Ctrl-A=all)" \
        --preview="echo '$log_dir/{}'; echo; tail -50 -- '$log_dir/{}'" \
        --preview-window=down)

    _lsf_open_logs_in_panes "$log_dir" "$selected_files"
}

function lsf_logs_all()
{
    if [[ -z $TMUX ]]; then
        echo "lsf_logs_all requires a tmux session"
        return 1
    fi

    if [[ -z $LOG_DIR ]]; then
        echo "LOG_DIR environment variable is not set"
        return 1
    fi

    if [[ ! -d "$LOG_DIR" ]]; then
        echo "Log directory does not exist: $LOG_DIR"
        return 1
    fi

    local query="${1:-}"

    # Find all log files under LOG_DIR (recursive, sorted by mtime)
    # Note: fzf returns selections in list order (top-to-bottom), not tab-selection order
    local selected_files=$(cd "$LOG_DIR" && find . -type f \( \
        -name "*.out" -o \
        -name "*.err" -o \
        -name "*.log" \
    \) -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2- | sed 's|^\./||' \
        | { [[ -n "$query" ]] && rg "$query" || cat; } \
        | fzf -m --bind ctrl-a:select-all \
        --header="Select log files from $LOG_DIR (Tab=multi-select, Ctrl-A=all)" \
        --preview="echo '$LOG_DIR/{}'; echo; tail -50 -- '$LOG_DIR/{}'" \
        --preview-window=down)

    _lsf_open_logs_in_panes "$LOG_DIR" "$selected_files"
}

function lsf_attach()
{
    local jobid=$(_lsf_jobs "$@")
    [[ -z "$jobid" ]] && return 0

    local exec_host=$(bjobs -json -o "exec_host" "$jobid" 2>/dev/null \
        | jq -r '.RECORDS[0].EXEC_HOST // empty')
    [[ -z "$exec_host" ]] && { battach -L $SHELL "$jobid"; return; }

    local nodes=(${(s/:/)exec_host})

    if [[ ${#nodes[@]} -le 1 ]]; then
        battach -L $SHELL "$jobid"
    else
        local node=$(printf '%s\n' "${nodes[@]}" | fzf --header="Select node ($jobid)")
        [[ -z "$node" ]] && return 0
        battach -m "$node" -L $SHELL "$jobid"
    fi
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
        bsub -Is -q preemptable -G grp_preemptable -gpu "num=${ngpu}:mode=shared:j_exclusive=yes" -R "rusage[mem=$((225*ngpu))GB]" $SHELL
    else
        bsub -Is -q preemptable -G grp_preemptable -gpu "num=${ngpu}:mode=shared:j_exclusive=yes" -R "rusage[mem=1800GB]" $SHELL
    fi
}

function lsf_alloc_grp_models()
{
    local ngpu=${1:-"1"}
    local mem
    if [ $ngpu -lt 8 ]; then
        mem=$((225*ngpu))
    else
        mem=1800
    fi
    bsub -J "grp_models_dev" \
        -q normal \
        -G grp_models \
        -gpu "num=${ngpu}:mode=shared:j_exclusive=yes" \
        -R "rusage[mem=${mem}GB]" \
        -o /dev/null -e /dev/null \
        sleep infinity
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
