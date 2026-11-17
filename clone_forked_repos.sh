#!/bin/bash

# Clone my GitHub forks; gc adds each one's upstream remote. Submodules are left uninitialized:
# pytorch's third_party alone is several GB, so init by hand where you intend to build.

source "$(dirname "$(readlink -f "$0")")/.git_fns.sh" || exit 1

# Fail instead of prompting for credentials on a machine whose key is not loaded.
export GIT_TERMINAL_PROMPT=0

ORG="garrett361"
REPOS=(
    transformers
    torchtitan
    pytorch
    nixl
    flash-linear-attention
    vllm
    flash-attention
    Megatron-LM
    ring-flash-attention
)
JOBS=4

preflight_github || exit 1

log_dir=$(mktemp -d) || exit 1
trap 'rm -rf "$log_dir"' EXIT

mkdir -p "$GITHUB/$ORG" || exit 1

# Concurrent clones would interleave their output, so each logs to its own file and only a one-line
# status per repo reaches the terminal live; the parent replays the full logs in list order below.
# Batch barrier rather than `wait -n`, absent in macOS bash 3.2.
launched=0
for repo in "${REPOS[@]}"; do
    if is_git_checkout "$GITHUB/$ORG/$repo"; then
        echo "[exists] $repo"
        echo 0 >"$log_dir/$repo.status"
        continue
    fi
    echo "[start] $repo"
    (
        start=$SECONDS
        clone_into_org "$ORG" "$repo" </dev/null >"$log_dir/$repo.log" 2>&1
        clone_status=$?
        echo "$clone_status" >"$log_dir/$repo.status"
        elapsed=$((SECONDS - start))
        result="ok"
        [ "$clone_status" -eq 0 ] || result="FAILED"
        printf '[%s %dm%02ds] %s\n' "$result" $((elapsed / 60)) $((elapsed % 60)) "$repo"
    ) &
    (( ++launched % JOBS )) || wait
done
# Mandatory: a list length that is not a multiple of JOBS leaves jobs outside the last barrier.
wait

skipped=""
for repo in "${REPOS[@]}"; do
    if [ -f "$log_dir/$repo.log" ]; then
        echo "--- $repo"
        cat "$log_dir/$repo.log"
    fi
    # String compare, not -ne: a missing status must read as failure, but [ "" -ne 0 ] succeeds.
    clone_status=$(cat "$log_dir/$repo.status" 2>/dev/null)
    [ "$clone_status" = "0" ] || skipped="$skipped $repo"
done

if [ -n "$skipped" ]; then
    echo "Skipped (clone failed):$skipped" >&2
fi
