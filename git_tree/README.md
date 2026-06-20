# git-tree

Cascading rebase tool for branch dependency chains.

When you work with stacked branches (A → B → C), adding commits to A means B and C need rebasing. `git-tree` tracks these dependencies and automates the cascade.

## Install

```sh
uv tool install -e /path/to/dotfiles/git_tree
```

This creates an isolated venv, installs `git-tree` in editable mode, and symlinks the executable to `~/.local/bin/git-tree`. Git auto-discovers it as `git tree`. The dotfiles `install.sh` handles this automatically.

## Usage

```sh
git tree                               # show dependency tree
git tree branch <name> [--path <dir>]  # create child branch (+ optional worktree)
git tree attach [parent]               # attach current branch to tree
git tree detach                        # remove current branch from tree
git tree propagate                     # cascade current branch's changes to descendants
git tree rebase <target>               # rebase current branch + descendants onto new base
git tree split                         # split current branch into parent + child
git tree push                          # push current branch + descendants (--force-with-lease)
```

## How it works

Dependencies are stored in git config:

```
git config branch.<name>.tree-parent <parent-branch>
```

No external files, no commit labels, no hooks. Works immediately after `git tree branch` or `git tree attach`.

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
