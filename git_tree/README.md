# git-tree

Cascading rebase tool for branch dependency chains.

When you work with stacked branches (A → B → C), adding commits to A means B and C need rebasing. `git-tree` tracks these dependencies and automates the cascade.

## Goals

git-tree manages branches that form a **dependency tree** — each branch stacks on one
parent, and a parent may have many children (a plain stack is the linear case). Each branch
lives in its own git worktree, so the whole tree stays checked out at once and you move
between branches without stashing.

Edit any branch with plain git (rebase, reorder, amend, add or drop commits, pull its
parent) and git-tree propagates that edit to every descendant, replaying only each branch's
own work so you never re-resolve a conflict you've already handled. It also provides the
commands to build and reshape the tree: create child branches with worktrees, split a branch
into parent and child, attach or detach branches, and tear down a subtree's worktrees.

It rewrites history, so it's for stacks you control and force-push, not shared branches. And
it stays a thin wrapper — non-trivial git commands are echoed with their output, so you can
see what it did and fall back to plain git.

## Install

```sh
uv tool install -e /path/to/dotfiles/git_tree
```

This creates an isolated venv, installs `git-tree` in editable mode, and symlinks the executable to `~/.local/bin/git-tree`. Git auto-discovers it as `git tree`. The dotfiles `install.sh` handles this automatically.

## Usage

```sh
git tree                               # show the current branch's tree
git tree --all                         # show every tree
git tree branch <name> <path>          # create or adopt a child branch with a worktree
git tree attach [parent]               # attach current branch to tree
git tree detach                        # remove current branch from tree (keeps branch + worktree)
git tree remove [branch]               # remove a subtree's worktrees + unregister its branches (keeps refs)
git tree propagate                     # cascade current branch's changes to descendants
git tree rebase <target>               # rebase current branch + descendants onto new base
git tree split                         # split current branch into parent + child
git tree push                          # push current branch + descendants (--force-with-lease)
```

## How it works

Each branch records two things in git config — no external files, no commit labels, no hooks:

```
git config branch.<name>.tree-parent-branch <parent-branch>   # which branch it stacks on
git config branch.<name>.tree-fork-commit   <commit>          # where it forks from that parent
```

`tree-parent-branch` is the structural edge; `tree-fork-commit` is the parent's tip the
branch was last rebased onto (set on `branch`/`attach`/`split` and updated after every
successful rebase). The fork commit is what lets a rebase replay *only* the branch's own
commits: once a parent moves ahead of its child, `merge-base(parent, child)` drifts off the
real fork, so the stored commit is the only reliable boundary. This is what makes an
interrupted propagate resumable, and keeps a reorder/split or `git pull --rebase` of a parent
from corrupting its descendants.

Works immediately after `git tree branch` or `git tree attach`, which record the fork commit.

### Propagate

After adding commits to a parent branch, run `git tree propagate` to rebase all descendants. Branches are processed in topological order (parents first). On conflict, the failing branch and its entire subtree are skipped.

### Rebase

When a parent branch gets squash-merged upstream, `git tree rebase <target>` rebases the current branch onto the merge target, excluding the old parent's commits, then cascades to descendants.

Equivalent to: `git rebase --onto <target> <fork-point>` + `git tree attach <target>` + `git tree propagate`.

### Push

`git tree push` pushes the current branch and all descendants with `--force-with-lease`. Branches that are stale (behind their parent) are skipped with a warning to run `propagate` first.

## Worktrees

All branches in the tree must have linked worktrees. Operations that touch multiple branches (propagate, rebase, push) verify this upfront and abort with an error listing any branches missing worktrees. Dirty worktrees are automatically stashed/popped during rebase.

## Development

```sh
uv sync
uv run pytest tests/ -q
uv run ruff check . --fix
uv run ruff format .
uv run ty check git_tree/
```
