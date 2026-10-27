#!/bin/bash
set -euo pipefail

ORG="PrimeIntellect-ai"
REPOS=(
    prime-rl
    renderers
    verifiers
)

repo_flags=()
for repo in "${REPOS[@]}"; do
    repo_flags+=(--repo "$ORG/$repo")
done

for role in --assignee --review-requested --reviewed-by; do
    gh search prs "$role" @me --state open "${repo_flags[@]}" \
        --json title,url --jq '.[] | "\(.title)\t\(.url)"'
done | sort -u
