# Clone helpers, shared by .commonrc and the repo-root clone_*_repos.sh scripts. Sourced from
# $DOTFILES rather than a $HOME symlink so a git pull cannot drop gc until install.sh reruns.

# Scripts sourcing this may run outside a login shell, where .commonrc has not exported GITHUB.
: "${GITHUB:=$HOME/github}"

function clone_from_host()
{
    local host="$1"
    local repo_name="$2"
    local org
    org=$(basename "$(pwd)")

    if [[ -z "$repo_name" ]]; then
        echo "Usage: gc <repo_name>" >&2
        return 1
    fi

    git clone "git@${host}:${org}/${repo_name}" && cd "$repo_name"
}

function add_upstream_if_fork()
{
    local host="$1"
    local q url_expr out ret name url

    if ! command -v gh >/dev/null 2>&1; then
        echo "upstream: gh not found; skipping fork check" >&2
        return 0
    fi

    url_expr='"git@'"$host"':\(.parent.owner.login)/\(.parent.name).git"'
    q="[.nameWithOwner, (if .isFork then $url_expr else \"\" end)] | @tsv"
    # gh's errors go to the terminal; capturing them would let a stray line into the remote URL.
    out=$(gh repo view --json isFork,parent,nameWithOwner -q "$q")
    ret=$?
    if [ "$ret" -ne 0 ]; then
        echo "upstream: gh repo view failed; no upstream added" >&2
        return 0
    fi

    name=${out%%$'\t'*}
    url=${out#*$'\t'}
    if [ -z "$url" ]; then
        echo "upstream: $name is not a fork"
        return 0
    fi

    if git remote add upstream "$url"; then
        echo "upstream: added $url"
    else
        echo "upstream: git remote add failed for $url" >&2
    fi
    return 0
}

function gc()
{
    clone_from_host "github.com" "$1" \
        && add_upstream_if_fork "github.com"
}

# True for a clone's .git directory and a linked worktree's .git file, false for the bare
# directory a killed clone leaves behind. Unlike --git-dir it never walks up to an enclosing repo.
function is_git_checkout()
{
    git rev-parse --resolve-git-dir "$1/.git" >/dev/null 2>&1
}

function clone_into_org()
{
    local org="$1" repo="$2"
    local dir="$GITHUB/$org/$repo"

    is_git_checkout "$dir" && return 0

    mkdir -p "$GITHUB/$org" || return 1
    ( cd "$GITHUB/$org" && gc "$repo" )
}

function preflight_github()
{
    # ssh -T exits 1 even on success, so match the banner. BatchMode fails rather than prompting,
    # which under the parallel clones would hang on /dev/tty behind redirected logs.
    if ! ssh -o BatchMode=yes -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
        echo "ssh to git@github.com failed; load a key into the agent first" >&2
        return 1
    fi

    gh auth status >/dev/null 2>&1 \
        || echo "gh is not authenticated; forks will not get an upstream remote" >&2
}
