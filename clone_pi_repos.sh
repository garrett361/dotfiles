#!/bin/bash

# Clone the PrimeIntellect-ai repos, each with a sibling <repo>-main worktree holding main, which
# serves as the git tree stack root. Re-running is a no-op: nothing existing is touched.

source "$(dirname "$(readlink -f "$0")")/.git_fns.sh" || exit 1

# Fail instead of prompting for credentials on a machine whose key is not loaded.
export GIT_TERMINAL_PROMPT=0

ORG="PrimeIntellect-ai"
REPOS=(
    prime-rl
    renderers
    verifiers
)

# git refuses to check out main twice, so the clone parks on a detached HEAD and the -main worktree
# takes the branch. Detached, not a scratch branch, so git tree's --parent default fails loudly.
add_main_worktree() {
    local dir="$1"
    local main_dir="${dir}-main"

    is_git_checkout "$main_dir" && return 0

    # An rm -rf'd worktree still owns main until git is told it is gone.
    git -C "$dir" worktree prune

    if [ "$(git -C "$dir" branch --show-current)" = "main" ]; then
        git -C "$dir" switch --detach || return 1
    fi

    if git -C "$dir" show-ref --verify --quiet refs/heads/main; then
        # main is checked out nowhere now, so this fast-forwards the branch itself; plain
        # `fetch origin main` would move only origin/main, leaving the stack root stale.
        git -C "$dir" fetch origin main:main \
            || echo "warning: could not fast-forward main in $dir" >&2
        git -C "$dir" worktree add "$main_dir" main
    else
        # A ref made by a fetch refspec carries no branch.main.remote, which git tree push reads
        # off a root, so local main has to be recreated with --track instead.
        git -C "$dir" fetch origin main \
            && git -C "$dir" worktree add --track -b main "$main_dir" origin/main
    fi
}

preflight_github || exit 1

skipped=""
for repo in "${REPOS[@]}"; do
    if ! clone_into_org "$ORG" "$repo"; then
        skipped="$skipped $repo"
        continue
    fi
    add_main_worktree "$GITHUB/$ORG/$repo" || skipped="$skipped $repo"
done

if [ -n "$skipped" ]; then
    echo "Skipped (clone or worktree failed):$skipped" >&2
fi
