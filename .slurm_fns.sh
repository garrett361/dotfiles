_slurm_jobs() {
    local query="" state=""
    local -a fzf_opts=()

    while [ $# -gt 0 ]; do
        case $1 in
            --multi)
                fzf_opts+=(-m --bind ctrl-a:select-all)
                shift
                ;;
            --state=*)
                state="${1#--state=}"
                shift
                ;;
            *)
                query="$1"
                shift
                ;;
        esac
    done

    local -a sq_args=(--me --noheader)
    [ -n "$state" ] && sq_args+=(--states="$state")

    local format="%.12i %.50j %.10u %.8T %.15P %.20N %.12M %.6D"
    local header
    header=$(squeue --me --format="$format" | head -1)

    local selected
    if [ -n "$query" ]; then
        selected=$(squeue "${sq_args[@]}" --format="$format" \
            | rg "$query" \
            | fzf "${fzf_opts[@]}" --header="$header")
    else
        selected=$(squeue "${sq_args[@]}" --format="$format" \
            | fzf "${fzf_opts[@]}" --header="$header")
    fi

    [ -n "$selected" ] && echo "$selected" | awk '{print $1}'
}

slurm_info() {
    local jobid
    jobid=$(_slurm_jobs "$@")
    [ -n "$jobid" ] && scontrol show job "$jobid"
}

slurm_logs() {
    if [ -z "$TMUX" ]; then
        echo "slurm_logs requires a tmux session"
        return 1
    fi

    local jobid
    jobid=$(_slurm_jobs "$@")
    [ -z "$jobid" ] && return 0

    local job_info stdout_path stderr_path
    job_info=$(scontrol show job "$jobid")

    if [ -z "$job_info" ]; then
        echo "Could not retrieve job info for $jobid (job may have finished)"
        return 1
    fi

    stdout_path=$(printf '%s\n' "$job_info" | sed -n 's/.* StdOut=\([^ ]*\).*/\1/p' | head -1)
    stderr_path=$(printf '%s\n' "$job_info" | sed -n 's/.* StdErr=\([^ ]*\).*/\1/p' | head -1)

    local -a cands=()
    [ -f "$stdout_path" ] && cands+=("$stdout_path")
    if [ -n "$stderr_path" ] && [ "$stderr_path" != "$stdout_path" ] && [ -f "$stderr_path" ]; then
        cands+=("$stderr_path")
    fi

    if [ ${#cands[@]} -eq 0 ]; then
        echo "No log files exist yet for job $jobid"
        echo "  StdOut: $stdout_path"
        [ -n "$stderr_path" ] && [ "$stderr_path" != "$stdout_path" ] && echo "  StdErr: $stderr_path"
        return 1
    fi

    local selected_files
    selected_files=$(printf '%s\n' "${cands[@]}" \
        | fzf -m --bind ctrl-a:select-all \
        --bind 'ctrl-y:execute-silent(printf %s {} | clip_copy)' \
        --header="Select log files for job $jobid (Tab=multi, Ctrl-A=all, Ctrl-Y=copy path)" \
        --preview="echo '{}'; echo; tail -50 -- '{}'" \
        --preview-window=down)
    [ -z "$selected_files" ] && return 0

    _open_logs_in_panes "$selected_files"
}

slurm_logs_all() {
    if [ -z "$TMUX" ]; then
        echo "slurm_logs_all requires a tmux session"
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
        --bind 'ctrl-y:execute-silent(printf "%s/%s" "$LOG_DIR" {} | clip_copy)' \
        --header="Select log files from $LOG_DIR (Tab=multi, Ctrl-A=all, Ctrl-Y=copy path)" \
        --preview="echo '$LOG_DIR/{}'; echo; tail -50 -- '$LOG_DIR/{}'" \
        --preview-window=down)
    [ -z "$selected_files" ] && return 0

    local abs_files
    abs_files=$(while IFS= read -r f; do
        [ -n "$f" ] && printf '%s/%s\n' "$LOG_DIR" "$f"
    done <<< "$selected_files")

    _open_logs_in_panes "$abs_files"
}

# One line per (running job, node), as "<jobid> <node> <nodecount> <label...>". The three
# machine-readable fields come first so that a job name containing spaces cannot shift them; the
# label is everything callers display and fzf searches.
_slurm_targets() {
    # Unwidthed format specifiers: the "%.12i" style used by _slurm_jobs truncates, and a
    # truncated job id fed to `srun --jobid=` fails. Split on "|" rather than whitespace, since
    # job names may contain spaces. The sed strips squeue's padding around the delimiters.
    local jobs
    jobs=$(squeue --me --states=RUNNING --noheader --format='%i|%j|%P|%N' 2>/dev/null \
        | sed 's/ *| */|/g; s/^ *//; s/ *$//')
    [ -z "$jobs" ] && return 1

    local out="" jobid name partition nodelist hostnames nodecount node marker first
    while IFS='|' read -r jobid name partition nodelist; do
        [ -z "$jobid" ] && continue
        # A pending or completing job reports no nodes; "(null)" would otherwise reach
        # `scontrol show hostnames` and come back as a selectable node.
        case "$nodelist" in
            "" | "(null)") continue ;;
        esac

        hostnames=$(scontrol show hostnames "$nodelist" 2>/dev/null)
        [ -z "$hostnames" ] && continue
        nodecount=$(printf '%s\n' "$hostnames" | grep -c .)

        first=1
        while IFS= read -r node; do
            [ -z "$node" ] && continue
            marker=""
            if [ "$first" = 1 ] && [ "$nodecount" -gt 1 ]; then
                marker="  (head)"
            fi
            first=0
            out="$out$(printf '%s %s %s %-10s %-24s %-14s %s%s' \
                "$jobid" "$node" "$nodecount" "$jobid" "$name" "$partition" "$node" "$marker")"$'\n'
        done <<< "$hostnames"
    done <<< "$jobs"

    [ -z "$out" ] && return 1
    printf '%s' "$out"
}

# fzf over _slurm_targets, printing the selected record. --local prepends an entry for the machine
# tmux itself is on and makes it the highlighted default; only tmux-slurm-shell passes it, so
# slurm_attach can never be handed the "local" token. Returns non-zero for anything that is not a
# selection, without distinguishing why: every caller treats those cases identically.
_slurm_pick_target() {
    local local_line="" host=""
    if [ "$1" = "--local" ]; then
        host=$(hostname -s)
        local_line=$(printf 'local %s 1 %-10s %s' "$host" "local" "$host")
        shift
    fi

    local targets
    targets=$(_slurm_targets)

    if [ -z "$targets" ]; then
        [ -z "$local_line" ] && return 1
        printf '%s\n' "$local_line"
        return 0
    fi

    local list="$targets"
    [ -n "$local_line" ] && list=$(printf '%s\n%s' "$local_line" "$targets")

    local header="Select where to open a shell"
    [ -n "$local_line" ] && header="Select where to open a shell (Esc stays on $host)"

    local selected
    # --with-nth hides the three machine-readable fields; fzf's default AWK-style delimiter needs
    # no --delimiter. The query is a filter, not a pre-selection, so an unmatched one is visible.
    selected=$(printf '%s\n' "$list" | fzf --with-nth=4.. --query="$*" --header="$header")
    [ -z "$selected" ] && return 1
    printf '%s\n' "$selected"
}

slurm_attach() {
    local target
    target=$(_slurm_pick_target "$@") || return 0

    local jobid node nodecount label
    read -r jobid node nodecount label <<< "$target"

    # -l makes the remote shell a login shell, so it runs .profile/.zprofile ->
    # .commonprofile -> .localrc; a plain "$SHELL" here never sources .localrc at all.
    local -a srun_cmd=(srun --jobid="$jobid" --overlap)
    # Single-node jobs keep the bare form. srun otherwise derives the task count from the
    # allocation, and pinning it to 1 can change GPU binding under a --gpus-per-task job.
    [ "$nodecount" -gt 1 ] && srun_cmd+=(--nodelist="$node" --ntasks=1)
    srun_cmd+=(--pty "$SHELL" -l)

    "${srun_cmd[@]}"
}

slurm_kill() {
    local job_ids_str
    job_ids_str=$(_slurm_jobs --multi "$@")
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
                    scancel "$id"
                    echo "Cancelled $id"
                fi
            done <<< "$job_ids_str"
            ;;
        *)
            echo "Delete aborted!"
            ;;
    esac
}

slurm_alloc() {
    local gpus=8
    local -a extra=()

    while [ $# -gt 0 ]; do
        case $1 in
            --gpus=*)
                gpus="${1#--gpus=}"
                shift
                ;;
            *)
                extra+=("$1")
                shift
                ;;
        esac
    done

    # A step inherits every GRES the job requested except those granted implicitly by --exclusive,
    # so without an explicit request slurm_attach's srun would land on the node with no GPUs.
    # salloc reports the job id and node itself, and slurm_attach finds the job by picker, so
    # there is nothing worth adding to its output.
    salloc --no-shell \
        --job-name=dev \
        --nodes=1 \
        --exclusive \
        --mem=0 \
        --gres="gpu:$gpus" \
        "${extra[@]}"
}

# Single letters are safe because .commonrc only sources this file on a slurm cluster. `r` is
# deliberately avoided for slurm_attach: it is a zsh builtin that re-runs the last command.
alias d="slurm_kill"
alias a="slurm_attach"
alias i="slurm_info"
