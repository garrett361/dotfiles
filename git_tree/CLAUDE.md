# git-tree

Cascading rebase tool for branch dependency chains. Manages branches that form trees (A → B → C) and automates propagating changes downstream.

## Design philosophy

git-tree is a deliberately **light wrapper around plain git**. It automates the bookkeeping of cascading rebases but should never obscure what git is doing. Two principles guide changes:

- **Minimal state**: dependency edges live in git config (see Architecture), not external files or commit labels. Anything git already knows is read from git, never duplicated.
- **Explicit and transparent**: prefer surfacing the underlying git operations over hiding them. Side-effecting commands echo the git invocation and reprint git's own output (`git_echo`); `git tree log` streams git directly. Only data-query git calls are captured silently. When in doubt, show the git command and its output rather than a hand-rolled summary.

## Install

```sh
uv tool install -e /path/to/dotfiles/git_tree   # editable, on PATH as git-tree
```

Handled by `dotfiles/install.sh`. No git alias needed — git auto-discovers `git-tree` on PATH as `git tree`.

## Dev commands

```sh
uv sync                          # install deps
uv run pytest tests/ -q          # run tests
uv run ruff check . --fix        # lint + autofix
uv run ruff format .             # format
uv run ty check git_tree/        # type check
```

## Architecture

Single module: `git_tree/cli.py`. All commands, git helpers, graph discovery, and tree display in one file. Entry point: `git_tree.cli:main` (registered as `git-tree` console script).

**Dependency storage** (git config, no external files/commit labels):
- `branch.<name>.tree-parent-branch <parent>` — the parent branch (structural edge)
- `branch.<name>.tree-fork-commit <commit>` — the parent tip this branch last rebased onto;
  the `--onto <old-base>` exclude boundary, set on branch/attach/split and updated after each
  successful rebase. Required for correct propagate once a parent moves ahead of its child
  (`merge-base` drifts). `_get_fork_commit`/`_set_fork_commit` manage it; a missing key falls
  back to `merge-base`.

**Key abstractions**:
- `Graph` dataclass: `parent_of`, `children_of`, `branches` dicts + `downstream_from()` BFS
- `BranchInfo` dataclass: `name`, `worktree` (optional Path), `fork_commit`, `is_dirty`. A tree has one remote, defined on its **root** (`branch.<root>.remote`); push and status resolve it via `_root_remote`/`root_of` rather than per-branch.
- `discover()`: reads worktree list + git config to build the graph

## Testing

Real git operations against isolated repos (no mocking). The `repo` fixture (`tests/conftest.py`) creates a bare origin + clone in `tmp_path` and `chdir`s into it. `RepoHelper` provides `commit()`, `branch()`, `checkout()`, `set_parent()`, `worktree()`, `push()`.

## Conventions

- Python 3.11+, stdlib only (no runtime deps)
- ruff for lint+format (line-length 100, select E/F/I/UP/B/SIM/TCH, TCH ignored in tests)
- ty for type checking
- Tests assert behavior, not implementation details
- Commits use conventional format with `(git_tree)` scope: `feat(git_tree): ...`, `fix(git_tree): ...`, `test(git_tree): ...`
