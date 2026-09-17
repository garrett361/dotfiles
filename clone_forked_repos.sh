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

# Concurrent clones would interleave their output, so each logs to its own file and the parent
# replays them in list order below. Batch barrier rather than `wait -n`, absent in macOS bash 3.2.
launched=0
for repo in "${REPOS[@]}"; do
    (
        clone_into_org "$ORG" "$repo" </dev/null >"$log_dir/$repo.log" 2>&1
        echo "$?" >"$log_dir/$repo.status"
    ) &
    (( ++launched % JOBS )) || wait
done
# Mandatory: a list length that is not a multiple of JOBS leaves jobs outside the last barrier.
wait

skipped=""
for repo in "${REPOS[@]}"; do
    echo "--- $repo"
    cat "$log_dir/$repo.log" 2>/dev/null
    # String compare, not -ne: a missing status must read as failure, but [ "" -ne 0 ] succeeds.
    clone_status=$(cat "$log_dir/$repo.status" 2>/dev/null)
    [ "$clone_status" = "0" ] || skipped="$skipped $repo"
done

if [ -n "$skipped" ]; then
    echo "Skipped (clone failed):$skipped" >&2
fi
