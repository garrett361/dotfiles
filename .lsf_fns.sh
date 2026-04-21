_lsf_jobs() {
    local user_filter="" query=""
    local -a fzf_opts=()

    while [ $# -gt 0 ]; do
        case $1 in
            --multi)
                fzf_opts+=(-m --bind ctrl-a:select-all)
                shift
                ;;
            *)
                if [ -z "$user_filter" ]; then
                    user_filter="$1"
                else
                    query="$1"
                fi
                shift
                ;;
        esac
    done

    user_filter="${user_filter:-$USER}"

    local header="JOBID JOB_NAME USER STAT QUEUE EXEC_HOST SUBMIT_TIME GPU_NUM"
    local selected
    if [ -n "$query" ]; then
        selected=$(bjobs -o "jobid job_name user stat queue exec_host submit_time gpu_num" \
            | rg "$user_filter" \
            | rg "$query" \
            | fzf "${fzf_opts[@]}" --header="$header")
    else
        selected=$(bjobs -o "jobid job_name user stat queue exec_host submit_time gpu_num" \
            | rg "$user_filter" \
            | fzf "${fzf_opts[@]}" --header="$header")
    fi

    [ -n "$selected" ] && echo "$selected" | awk '{print $1}'
}

lsf_info() {
    local jobid
    jobid=$(_lsf_jobs "$@")
    [ -n "$jobid" ] && bjobs -l "$jobid"
}

lsf_logs() {
    if [ -z "$TMUX" ]; then
        echo "lsf_logs requires a tmux session"
        return 1
    fi

    local query=""
    if [ $# -gt 0 ]; then
        query="$1"
        shift
    fi

    local jobid
    jobid=$(_lsf_jobs "$@")
    [ -z "$jobid" ] && return 0

    local job_json output_file
    job_json=$(bjobs -o "output_file" -json "$jobid" 2>/dev/null)
    output_file=$(echo "$job_json" | jq -r '.RECORDS[0].OUTPUT_FILE // empty')

    if [ -z "$output_file" ]; then
        echo "Could not determine log directory for job $jobid"
        return 1
    fi

    local log_dir="${LOG_DIR:-$(dirname "$output_file")}"

    if [ ! -d "$log_dir" ]; then
        echo "Log directory does not exist: $log_dir"
        return 1
    fi

    local selected_files
    selected_files=$(cd "$log_dir" && find . -maxdepth 1 \( \
        -name "*_${jobid}.out" -o \
        -name "*_${jobid}.err" -o \
        -name "*_${jobid}.log" -o \
        -name "*_${jobid}_*.log" \
    \) 2>/dev/null | sed 's|^\./||' | sort \
        | if [ -n "$query" ]; then rg "$query"; else cat; fi \
        | fzf -m --bind ctrl-a:select-all \
        --header="Select log files for job $jobid (Tab=multi-select, Ctrl-A=all)" \
        --preview="echo '$log_dir/{}'; echo; tail -50 -- '$log_dir/{}'" \
        --preview-window=down)
    [ -z "$selected_files" ] && return 0

    local abs_files
    abs_files=$(while IFS= read -r f; do
        [ -n "$f" ] && printf '%s/%s\n' "$log_dir" "$f"
    done <<< "$selected_files")

    _open_logs_in_panes "$abs_files"
}

lsf_logs_all() {
    if [ -z "$TMUX" ]; then
        echo "lsf_logs_all requires a tmux session"
        return 1
    fi

    if [ -z "$LOG_DIR" ]; then
        echo "LOG_DIR environment variable is not set"
        return 1
    fi

    if [ ! -d "$LOG_DIR" ]; then
        echo "Log directory does not exist: $LOG_DIR"
        return 1
    fi

    local query="${1:-}"
    local selected_files
    selected_files=$(cd "$LOG_DIR" && find . -type f \( \
        -name "*.out" -o -name "*.err" -o -name "*.log" \
    \) -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2- | sed 's|^\./||' \
        | if [ -n "$query" ]; then rg "$query"; else cat; fi \
        | fzf -m --bind ctrl-a:select-all \
        --header="Select log files from $LOG_DIR (Tab=multi-select, Ctrl-A=all)" \
        --preview="echo '$LOG_DIR/{}'; echo; tail -50 -- '$LOG_DIR/{}'" \
        --preview-window=down)
    [ -z "$selected_files" ] && return 0

    local abs_files
    abs_files=$(while IFS= read -r f; do
        [ -n "$f" ] && printf '%s/%s\n' "$LOG_DIR" "$f"
    done <<< "$selected_files")

    _open_logs_in_panes "$abs_files"
}

lsf_attach() {
    local jobid
    jobid=$(_lsf_jobs "$@")
    [ -z "$jobid" ] && return 0

    local exec_host
    exec_host=$(bjobs -json -o "exec_host" "$jobid" 2>/dev/null \
        | jq -r '.RECORDS[0].EXEC_HOST // empty')

    if [ -z "$exec_host" ]; then
        battach -L "$SHELL" "$jobid"
        return
    fi

    local -a nodes=()
    IFS=':' read -ra nodes <<< "$exec_host"
    local node_count=${#nodes[@]}

    if [ "$node_count" -le 1 ]; then
        battach -L "$SHELL" "$jobid"
    else
        local node
        node=$(printf '%s\n' "${nodes[@]}" | fzf --header="Select node ($jobid)")
        [ -z "$node" ] && return 0
        battach -m "$node" -L "$SHELL" "$jobid"
    fi
}

lsf_kill() {
    local job_ids_str
    job_ids_str=$(_lsf_jobs --multi "$@")
    [ -z "$job_ids_str" ] && return 0

    echo "Delete these jobs? [y/N]"
    while IFS= read -r id; do
        [ -n "$id" ] && echo "  $id"
    done <<< "$job_ids_str"

    read -r response
    case "$response" in
        [yY][eE][sS]|[yY])
            while IFS= read -r id; do
                if [ -n "$id" ]; then
                    bkill "$id"
                    echo "Killing $id"
                fi
            done <<< "$job_ids_str"
            ;;
        *)
            echo "Delete aborted!"
            ;;
    esac
}

lsf_alloc() {
    local ngpu=${1:-"1"}
    if [ "$ngpu" -lt 8 ]; then
        bsub -Is -q preemptable -G grp_preemptable -gpu "num=${ngpu}:mode=shared:j_exclusive=yes" -R "rusage[mem=$((225*ngpu))GB]" "$SHELL"
    else
        bsub -Is -q preemptable -G grp_preemptable -gpu "num=${ngpu}:mode=shared:j_exclusive=yes" -R "rusage[mem=1800GB]" "$SHELL"
    fi
}

lsf_alloc_grp_models() {
    local ngpu=${1:-"1"}
    local mem
    if [ "$ngpu" -lt 8 ]; then
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

lsf_jupyterlab() {
    bsub -I -gpu "num=1:j_exclusive=yes" jupyter-lab --no-browser --port="${1:-8880}"
}
