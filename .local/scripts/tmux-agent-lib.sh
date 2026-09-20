# tmux-agent-lib.sh: the agent records tmux-agent-picker and tmux-agent-counts share. Sourced, so
# no shebang and no execute bit. Holds what the two must agree on, which is where state comes from
# and how each harness spells it; presentation stays in each caller, as does PATH, since only the
# picker needs fzf on it.
#
# Colours must agree but cannot be shared: working green, blocked bright red, idle bright yellow.

# get_deps.sh already drives Claude with CLAUDE_CONFIG_DIR, so it is a real knob on this machine.
SESSIONS_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/sessions"

# busy/shell to working and waiting to blocked is Claude's own collapse, not an interpretation.
#
# The tmux field is written once and can be stale or the literal ":.". Scanned for the last %N
# rather than split on "." because a session name may contain a dot; ":." yields "" and is dropped
# at the join, since tmux resolves it to the *current* pane.
#
# statusUpdatedAt moves on transition, so it dates the state rather than measuring idleness.
CLAUDE_MAP='
[ .[]
  | select(type == "object" and .pid != null)
  | { pid: (.pid | tostring),
      agent: "claude",
      cwd: (.cwd // ""),
      tmux_pane: ((.tmux // "") | [scan("%[0-9]+")] | last // ""),
      status: (if (.status == "busy" or .status == "shell") then "working"
               elif .status == "waiting" then "blocked"
               else "idle" end),
      waitingFor: (.waitingFor // ""),
      name: (.name // ""),
      updatedAt: (.statusUpdatedAt // .updatedAt // 0) } ]'

# *.json and never *: the directory also holds mode-0600 <pid>.<sha256>.key files containing
# {"peerToken":...}, which are valid JSON objects and would be slurped and then silently dropped.
# Nothing here prints a file's contents on error, only its path.
claude_records() {
    local files=() f out
    for f in "$SESSIONS_DIR"/*.json; do
        [[ -f "$f" ]] && files+=("$f")
    done

    # jq with no file arguments reads stdin and would hang inside an fzf reload. An empty registry
    # is ordinary on a fresh boot, so this is an early return, not a guard that happens to work.
    if [[ ${#files[@]} -eq 0 ]]; then
        printf '[]'
        return 0
    fi

    if out=$(jq -s -c "$CLAUDE_MAP" "${files[@]}" 2> /dev/null) && [[ -n "$out" ]]; then
        printf '%s' "$out"
        return 0
    fi

    # A file caught mid-write aborts the whole jq -s slurp, so retry per file and lose only that
    # one. The array is reassembled by a second jq rather than by hand: jq runs its program once
    # per input value, so a file holding two objects would emit two records and hand-placed commas
    # would splice them in as invalid JSON, losing every healthy record to one odd file.
    for f in "${files[@]}"; do
        jq -c "[.] | $CLAUDE_MAP | .[]" "$f" 2> /dev/null
    done | jq -s -c '.' 2> /dev/null
}

# Included in front of every consumer's jq program, so a rule that both must apply cannot be
# applied by only one of them.
#
# One pane hosts one agent. Two records can still claim the same one, since a stale registry entry
# outlives the pane it named and three sources now name panes independently, and the newest
# transition is the likelier occupant. Consumers apply this after their own liveness filter, never
# before: a dead record winning the group would take the live one with it.
JQ_PRELUDE='
def dedupe_by_pane:
    group_by(.tmux_pane) | map(if length == 1 then .[0] else (sort_by(.updatedAt) | last) end);
'

# THE SEAM. Everything downstream consumes the uniform record and knows nothing about its source.
# Each reader normalizes its own vocabulary and takes the pane table, so the three cost one tmux
# call between them, and one that produces nothing drops out of the slurp rather than emptying it.
# None of the three needs a hook or an extension installed, which was the constraint.
#
# $2 is the prime-agent cache TTL; see prime_agent_records_cached.
agent_records() {
    jq -s -c 'add // []' \
        <(claude_records) <(codex_records "$1") <(prime_agent_records_cached "$1" "$2") \
        2> /dev/null
}

# codex puts its run state in the terminal title with a plain OSC 0, which tmux exposes as
# pane_title, so all three states read without a hook. Rules follow herdr's codex.toml, where the
# title rules outrank its screen-scraping ones.
#
# Hooks were rejected, not overlooked: get_deps.sh has herdr overwrite ~/.codex/hooks.json, hooks
# are SHA-256 trust-pinned so editing one silently disables it, and nothing fires when a permission
# request is answered, so a hook-authored blocked state can stick after a denial.
#
# No updatedAt, so these rows show no age.
codex_records() {
    printf '%s' "$1" | jq -R -s -c '
        def title_of: .[4] // "";
        [ split("\n")[] | select(length > 0) | split("\t")
          | select(.[2] == "codex")
          | title_of as $t
          | { pid: "",
              agent: "codex",
              cwd: (.[3] // ""),
              tmux_pane: .[0],
              status: (if ($t | test("Action Required")) then "blocked"
                       elif ($t | test("(?:^| )[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏](?: |$)")) then "working"
                       else "idle" end),
              waitingFor: (if ($t | test("Action Required")) then "action required" else "" end),
              # The run-state item leads the title and is state, not content, so it is stripped
              # the same way Claude sigil is, along with the separator codex puts after it. Both
              # spellings of the blocked marker animate. A title that is only run state strips to
              # empty and the fallback chain reaches the cwd basename, which says more than Ready.
              name: ($t | sub("^(\\s*(\\[\\s*[!.]\\s*\\]|[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]|Action Required|Ready)\\s*(-\\s*)?)+"; "")),
              updatedAt: 0 }
          # A title that was only run state strips to empty, and the shared fallback would then
          # recover the same words from the raw pane title and restate the status column. The
          # directory is the useful thing to show instead.
          | if .name == "" then .name = (.cwd | split("/") | last) else . end ]' 2> /dev/null
}

# prime-agent runs sessions in detached daemon workers, so its data carries no pid and no pane.
# The join is cwd against panes running prime-agent, which is also why unattached sessions are
# skipped: nothing to jump to. Reading the pane from the worker environment would work but that
# environment carries API keys, which is why the Claude reader stopped doing it too.
#
# Working and idle only. prime-agent cannot report blocked: the event its own herdr reporter waits
# on has no emitter in the product. A property of prime-agent, not a gap here.
# Every early return prints an empty array rather than nothing: the cache wrapper treats a file
# that does not start with [ as malformed, so a silent success would poison it on every machine
# without prime-agent.
prime_agent_records() {
    command -v prime-agent > /dev/null 2>&1 || { printf '[]'; return 0; }
    # With no prime-agent pane the query cannot produce a row however it answers, and the table is
    # already in hand, so this keeps a machine that never runs it from paying for the subprocess.
    printf '%s' "$1" | cut -f3 | grep -qx 'prime-agent' || { printf '[]'; return 0; }
    local out
    out=$(prime-agent list --all --json 2> /dev/null) || { printf '[]'; return 0; }
    [[ -n "$out" ]] || { printf '[]'; return 0; }
    printf '%s' "$out" | jq -c --arg panes "$1" '
        ([$panes | split("\n")[] | select(length > 0) | split("\t")
          | select(.[2] == "prime-agent")
          | {key: (.[3] // ""), value: .[0]}] | from_entries) as $byCwd
        | [ .sessions[]?
            | select((.attachedClients // 0) > 0)
            | select($byCwd[.cwd // ""] != null)
            | { pid: "",
                agent: "prime-agent",
                cwd: (.cwd // ""),
                tmux_pane: $byCwd[.cwd],
                status: (if (.activity == "working" or .activity == "executing")
                         then "working" else "idle" end),
                waitingFor: "",
                # summary is written by the model and reads like a task title, which is exactly
                # what this column wants; firstMessage is the fallback for a session too young to
                # have one.
                name: (.summary // .firstMessage // ""),
                updatedAt: (try ((.lastActivityAt // "")
                                 | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000)
                            catch 0) } ]' 2> /dev/null
}

# The pid comes from .pid, not the filename: not every file there is named after one. kill is a
# builtin, so this is free, and it only catches the window after a SIGKILL.
live_pids() {
    printf '%s' "$1" | jq -r '.[].pid' 2> /dev/null | while read -r pid; do
        kill -0 "$pid" 2> /dev/null && printf '%s\n' "$pid"
    done
}

# One call for the whole server rather than a display-message per row, which on a timer would be a
# process per agent per tick. pane_title is last because it is the only field that could contain a
# tab, so a pathological title loses its own tail instead of the row. current_command and
# current_path feed the codex and prime-agent readers, which build their rows out of this table.
pane_table() {
    tmux list-panes -a \
        -F $'#{pane_id}\t#{session_name}\t#{pane_current_command}\t#{pane_current_path}\t#{pane_title}' \
        2> /dev/null
}

# prime_agent_records costs about 83 ms, charged once per attached client per status-interval in
# the bar, so it is cached. The TTL is an argument because the picker reloads every two seconds and
# should feel live where the bar ticks at fifteen and does not care.
#
# No lock: a stampede costs what the uncached reader costs anyway.
prime_agent_records_cached() {
    local panes=$1 ttl=$2 dir file tmp mtime now first
    dir="${XDG_CACHE_HOME:-$HOME/.cache}/tmux-agent"
    file="$dir/prime-agent.json"

    # Tried rather than branched on uname, since neither stat accepts the other's flag. Both
    # failing leaves mtime empty and the cache counts as cold.
    mtime=$(stat -f %m "$file" 2> /dev/null || stat -c %Y "$file" 2> /dev/null)
    now=$(date +%s)
    if [[ -n "$mtime" ]] && [[ $((now - mtime)) -lt $ttl ]]; then
        # A malformed cache would abort the agent_records slurp and take the other two harnesses
        # with it. One builtin byte catches anything that is not an array; a real validation would
        # cost a jq per call and defeat the cache.
        { IFS= read -r -n1 first < "$file"; } 2> /dev/null
        if [[ "$first" == "[" ]]; then
            cat "$file" 2> /dev/null
            return 0
        fi
    fi

    mkdir -p "$dir" 2> /dev/null
    # Temp file then rename, so a concurrent reader sees old or new and never half of either.
    tmp=$(mktemp "$dir/.prime-agent.XXXXXX" 2> /dev/null) || {
        prime_agent_records "$panes"
        return 0
    }
    # Guarded on the producer, not just the rename: an atomic rename of a half-produced file is
    # exactly how a malformed cache gets made.
    if prime_agent_records "$panes" > "$tmp" 2> /dev/null; then
        # Emitted from the temp file, not from $file: a failed rename would otherwise throw away
        # records already in hand, and re-reading $file races whoever renamed over it.
        cat "$tmp" 2> /dev/null
        mv -f "$tmp" "$file" 2> /dev/null || rm -f "$tmp" 2> /dev/null
    else
        rm -f "$tmp" 2> /dev/null
    fi
}
