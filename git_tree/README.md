# git-tree

Cascading rebase tool for branch dependency chains.

When you work with stacked branches (A → B → C), adding commits to A means B and C need rebasing. `git-tree` tracks these dependencies and automates the cascade.

## Install

```sh
uv pip install -e .
```

This installs `git-tree` as a console script. Git auto-discovers it as `git tree`.

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

### Push

`git tree push` pushes the current branch and all descendants with `--force-with-lease`. Branches that are stale (behind their parent) are skipped with a warning to run `propagate` first.

## Worktrees

Worktrees are optional. The tool operates on branches — worktrees are a convenience for active development. Branches with worktrees get automatic stash/pop during rebase; branches without worktrees are rebased directly.

## Development

```sh
uv sync
uv run pytest tests/ -q
uv run ruff check . --fix
uv run ruff format .
uv run ty check git_tree/
```
