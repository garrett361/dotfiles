"""git-tree: Cascading rebase tool for branch dependency chains."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

class TreeError(SystemExit):
    """Raised by helpers to exit with a user-facing message."""

    def __init__(self, msg: str):
        print(msg, file=sys.stderr)
        super().__init__(1)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(
    *args: str,
    check: bool = True,
    capture: bool = True,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
        cwd=cwd,
        env={**os.environ, **env} if env else None,
    )


def git(
    *args: str,
    cwd: Path | str | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> str:
    result = _run("git", *args, cwd=cwd, check=check, env=env)
    return result.stdout.strip()


def git_lines(*args: str, cwd: Path | str | None = None) -> list[str]:
    out = git(*args, cwd=cwd)
    return out.splitlines() if out else []


def git_ok(*args: str, cwd: Path | str | None = None, env: dict[str, str] | None = None) -> bool:
    result = _run("git", *args, check=False, cwd=cwd, env=env)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BranchInfo:
    name: str
    worktree: Path | None = None
    remote: str | None = None

    @property
    def is_dirty(self) -> bool:
        if self.worktree is None:
            return False
        out = git("status", "--porcelain", cwd=self.worktree)
        return bool(out)


@dataclass
class Graph:
    parent_of: dict[str, str] = field(default_factory=dict)
    children_of: dict[str, list[str]] = field(default_factory=dict)
    branches: dict[str, BranchInfo] = field(default_factory=dict)

    def downstream_from(self, branch: str) -> list[str]:
        """Return all descendants in topological order (BFS, parents before children)."""
        result: list[str] = []
        queue = list(self.children_of.get(branch, []))
        visited: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            result.append(current)
            queue.extend(self.children_of.get(current, []))
        return result


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def current_branch() -> str:
    proc = _run("git", "rev-parse", "--abbrev-ref", "HEAD", check=False)
    if proc.returncode != 0:
        msg = proc.stderr.strip() if proc.stderr else "not on a branch"
        raise TreeError(f"fatal: {msg}")
    return proc.stdout.strip()


def main_branch() -> str:
    for candidate in ("main", "master"):
        if git_ok("rev-parse", "--verify", candidate):
            return candidate
    return "main"


def discover() -> Graph:
    graph = Graph()

    worktree_map: dict[str, Path] = {}
    porcelain = git("worktree", "list", "--porcelain")
    current_path: Path | None = None
    worktree_count = 0
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.split(" ", 1)[1])
            worktree_count += 1
        elif line.startswith("branch refs/heads/"):
            branch_name = line.removeprefix("branch refs/heads/")
            # Skip the main worktree (first entry) — only track added worktrees
            if current_path is not None and worktree_count > 1:
                worktree_map[branch_name] = current_path

    all_branches = git_lines("for-each-ref", "--format=%(refname:short)", "refs/heads/")

    for branch in all_branches:
        parent = git("config", f"branch.{branch}.tree-parent", check=False)
        if not parent:
            continue

        remote = git("config", f"branch.{branch}.remote", check=False) or None
        info = BranchInfo(
            name=branch,
            worktree=worktree_map.get(branch),
            remote=remote,
        )
        graph.branches[branch] = info
        graph.parent_of[branch] = parent
        graph.children_of.setdefault(parent, []).append(branch)

    return graph


# ---------------------------------------------------------------------------
# Tree display
# ---------------------------------------------------------------------------

BOX_PIPE = "│"
BOX_TEE = "├──"
BOX_ELBOW = "└──"
BOX_SPACE = "   "
BOX_PIPE_SPACE = "│  "


def _pending_count(parent: str, child: str) -> int:
    """Count commits on parent that child hasn't incorporated yet."""
    base = git("merge-base", parent, child, check=False)
    if not base:
        return 0
    out = git("rev-list", "--count", f"{base}..{parent}")
    return int(out) if out else 0


def format_tree(
    graph: Graph,
    root: str | None = None,
    show_counts: bool = False,
    current: str | None = None,
) -> str:
    if root is None:
        root = main_branch()

    marker = "* " if current == root else ""
    lines: list[str] = [f"{marker}{root}"]
    children = graph.children_of.get(root, [])
    _format_subtree(graph, children, "", lines, show_counts=show_counts, current=current)
    return "\n".join(lines)


def _format_subtree(
    graph: Graph,
    children: list[str],
    prefix: str,
    lines: list[str],
    *,
    show_counts: bool = False,
    current: str | None = None,
) -> None:
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        connector = BOX_ELBOW if is_last else BOX_TEE

        info = graph.branches.get(child)
        annotation = ""
        if info and info.worktree:
            wt = str(info.worktree).replace(str(Path.home()), "~")
            dirty = "  (dirty)" if info.is_dirty else ""
            annotation = f"  {wt}{dirty}"
        elif info:
            annotation = "  (no worktree)"

        if show_counts:
            parent = graph.parent_of.get(child, "")
            if parent:
                n = _pending_count(parent, child)
                if n > 0:
                    annotation += f"  [{n} new]"

        marker = "* " if current == child else ""
        lines.append(f"{prefix}{connector} {marker}{child}{annotation}")

        grandchildren = graph.children_of.get(child, [])
        if grandchildren:
            next_prefix = prefix + (BOX_SPACE if is_last else BOX_PIPE_SPACE)
            _format_subtree(
                graph, grandchildren, next_prefix, lines,
                show_counts=show_counts, current=current,
            )


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------


def confirm(message: str) -> bool:
    try:
        response = input(f"{message} [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return response.strip().lower() in ("y", "yes")


# ---------------------------------------------------------------------------
# fzf helpers
# ---------------------------------------------------------------------------


def fzf_select(
    items: list[str],
    *,
    multi: bool = False,
    prompt: str = "> ",
    preview: str | None = None,
    header: str | None = None,
) -> list[str]:
    cmd = ["fzf"]
    if multi:
        cmd.extend(["--multi", "--bind", "ctrl-a:select-all,ctrl-d:deselect-all"])
    cmd.extend(["--prompt", prompt])
    if preview:
        cmd.extend(["--preview", preview])
    if header:
        cmd.extend(["--header", header])

    try:
        result = subprocess.run(
            cmd,
            input="\n".join(items),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _fallback_select(items, multi=multi)


def _fallback_select(items: list[str], *, multi: bool) -> list[str]:
    print("Select (comma-separated numbers):" if multi else "Select:")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    try:
        response = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return []
    if not response:
        return []
    indices = [int(x.strip()) - 1 for x in response.split(",") if x.strip().isdigit()]
    selected = [items[i] for i in indices if 0 <= i < len(items)]
    if not multi:
        return selected[:1]
    return selected


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_tree(_args: argparse.Namespace) -> None:
    graph = discover()
    raw = git("rev-parse", "--abbrev-ref", "HEAD", check=False)
    current = None if (not raw or raw == "HEAD") else raw
    print(format_tree(graph, current=current, show_counts=True))
    if not graph.parent_of:
        print("  (no branches registered — use `git tree attach` or `git tree branch`)")


def cmd_branch(args: argparse.Namespace) -> None:
    parent = current_branch()
    name: str = args.name
    path: str | None = args.path

    if path:
        git("worktree", "add", path, "-b", name)
    else:
        git("branch", name)

    git("config", f"branch.{name}.tree-parent", parent)

    remote = git("config", f"branch.{parent}.remote", check=False)
    if remote:
        git("config", f"branch.{name}.remote", remote)

    wt_msg = f" with worktree at {path}" if path else ""
    print(f"Created branch {name} (parent: {parent}){wt_msg}")


def cmd_attach(args: argparse.Namespace) -> None:
    branch = current_branch()
    parent: str | None = args.parent

    if not parent:
        all_branches = git_lines("for-each-ref", "--format=%(refname:short)", "refs/heads/")
        candidates = [b for b in all_branches if b != branch]
        if not candidates:
            raise TreeError("No other branches available.")
        selected = fzf_select(candidates, prompt="Select parent> ", header="Choose parent branch")
        if not selected:
            raise SystemExit(1)
        parent = selected[0]

    if not git_ok("merge-base", "--is-ancestor", parent, branch):
        merge_base = git("merge-base", parent, branch)
        parent_tip = git("rev-parse", parent)
        if merge_base != parent_tip:
            print(f"Warning: {branch} does not appear to descend from {parent}.", file=sys.stderr)

    git("config", f"branch.{branch}.tree-parent", parent)
    print(f"Attached {branch} to {parent}")


def cmd_detach(args: argparse.Namespace) -> None:
    branch = getattr(args, "branch", None) or current_branch()
    parent = git("config", f"branch.{branch}.tree-parent", check=False)
    if not parent:
        raise TreeError(f"{branch} is not in the tree.")

    git("config", "--unset", f"branch.{branch}.tree-parent")
    print(f"Detached {branch} (was child of {parent})")


# [empty-patch handling]
#
# git rebase --onto can exit non-zero without producing merge conflicts.
# Two distinct cases:
#
# 1. No rebase started (REBASE_HEAD absent): git determined there was nothing
#    to replay and exited. The branch ref may already be updated. Return "ok".
#
# 2. Rebase started but stopped on an empty patch (REBASE_HEAD present, no
#    unmerged files): a commit's changes are already in the target. Common when
#    cascading through branches with no unique commits. Loop --skip until done
#    or a real conflict appears. Must loop — multi-commit branches can have
#    several empty patches in sequence.


def _rebase_in_progress(cwd: Path | None) -> bool:
    return git_ok("rev-parse", "--verify", "REBASE_HEAD", cwd=cwd)


def _skip_empty_commits(child: str, parent: str, cwd: Path | None) -> str | None:
    """Loop --skip until rebase finishes or a real conflict appears. Returns None if
    a real conflict was hit (rebase still in progress for user to resolve)."""
    while _rebase_in_progress(cwd):
        unmerged = git("ls-files", "--unmerged", cwd=cwd, check=False)
        if unmerged.strip():
            return None
        if not git_ok("rebase", "--skip", cwd=cwd):
            git("rebase", "--abort", cwd=cwd, check=False)
            raise TreeError(f"rebase of {child} onto {parent}: --skip failed unexpectedly")
    return "ok (skipped empty)"


def _rebase_onto(
    child: str,
    parent: str,
    fork_point: str,
    cwd: Path | None,
    auto_rerere: bool,
    stashed: bool,
    main_stashed: bool = False,
) -> str:
    """Attempt rebase of child onto parent. Returns status or exits on unresolved conflict."""
    if cwd:
        result = _run("git", "rebase", "--onto", parent, fork_point, cwd=cwd, check=False)
    else:
        result = _run("git", "rebase", "--onto", parent, fork_point, child, check=False)

    if result.returncode == 0:
        return "ok"

    if not _rebase_in_progress(cwd):
        stderr = result.stderr.strip() if result.stderr else ""
        if any(line.startswith(("error:", "fatal:")) for line in stderr.splitlines()):
            raise TreeError(f"rebase of {child} onto {parent} failed:\n{stderr}")
        return "ok"

    unmerged = git("ls-files", "--unmerged", cwd=cwd, check=False)
    if not unmerged.strip():
        status = _skip_empty_commits(child, parent, cwd)
        if status is not None:
            return status
        _conflict_exit(child, parent, cwd, stashed, main_stashed)

    if not auto_rerere:
        _conflict_exit(child, parent, cwd, stashed, main_stashed)

    while True:
        git("rerere", cwd=cwd, check=False)

        remaining = git("rerere", "remaining", cwd=cwd, check=False)
        if remaining.strip():
            _conflict_exit(child, parent, cwd, stashed, main_stashed)

        git("add", "-u", cwd=cwd)

        continued = git_ok("rebase", "--continue", cwd=cwd, env={"GIT_EDITOR": "true"})
        if continued:
            return "ok (rerere)"

        # --continue stopped again — new conflict or empty patch?
        new_unmerged = git("ls-files", "--unmerged", cwd=cwd, check=False)
        if not new_unmerged.strip():
            status = _skip_empty_commits(child, parent, cwd)
            if status is not None:
                return "ok (rerere)"
            _conflict_exit(child, parent, cwd, stashed, main_stashed)


def _conflict_exit(
    child: str, parent: str, cwd: Path | None, stashed: bool, main_stashed: bool = False,
) -> NoReturn:
    lines = [f"\nCONFLICT while rebasing {child} onto {parent}"]
    if cwd:
        lines.append(f"Resolve conflicts in {cwd}, then run: git rebase --continue")
    else:
        lines.append("Resolve conflicts, then run: git rebase --continue")
    if stashed:
        if cwd:
            lines.append(f"Note: dirty worktree was stashed — run: cd {cwd} && git stash pop")
        else:
            lines.append("Note: dirty worktree was stashed — run `git stash pop` after resolving")
    if main_stashed:
        lines.append("Note: main worktree was stashed — run `git stash pop` after resolving")
    raise TreeError("\n".join(lines))


def cmd_propagate(args: argparse.Namespace) -> None:
    branch = getattr(args, "branch", None) or current_branch()
    graph = discover()

    descendants = graph.downstream_from(branch)
    if not descendants:
        print("No descendants to propagate to.")
        return

    print(f"Propagating from {branch}:")
    subtree_lines = format_tree(graph, root=branch, show_counts=True).splitlines()[1:]
    for line in subtree_lines:
        print(line)
    print()

    if getattr(args, "dry", False) or not confirm("Proceed?"):
        return

    auto_rerere = not getattr(args, "no_auto_rerere", False)
    results: list[tuple[str, str]] = []

    # [main worktree stash] Non-worktree branches rebase in the main worktree via
    # `git rebase --onto parent fork child`, which checks out child in the main worktree.
    # If the main worktree is dirty, git refuses (exit 1, no REBASE_HEAD). Stash first,
    # then restore HEAD + pop after the loop.
    original_branch = current_branch()
    needs_main_wt = any(
        not (graph.branches.get(c) and graph.branches[c].worktree) for c in descendants
    )
    main_stashed = False
    if needs_main_wt and bool(git("status", "--porcelain", check=False)):
        result = _run("git", "stash", check=False)
        main_stashed = "Saved working directory" in result.stdout

    for child in descendants:
        parent_of_child = graph.parent_of[child]

        info = graph.branches.get(child)
        stashed = False

        if info and info.worktree and info.is_dirty:
            result = _run("git", "stash", check=False, cwd=info.worktree)
            stashed = "Saved working directory" in result.stdout

        fork_point = git("merge-base", parent_of_child, child)
        wt_cwd = info.worktree if info and info.worktree else None

        status = _rebase_onto(
            child, parent_of_child, fork_point, wt_cwd, auto_rerere, stashed, main_stashed
        )

        if stashed and info and info.worktree:
            pop_ok = git_ok("stash", "pop", cwd=info.worktree)
            if not pop_ok:
                results.append((child, "rebased (stash pop conflict - resolve manually)"))
                continue

        results.append((child, status))

    if needs_main_wt:
        git("checkout", original_branch, check=False)
    if main_stashed:
        if not git_ok("stash", "pop"):
            print(
                "Warning: could not pop main worktree stash — run `git stash pop` manually",
                file=sys.stderr,
            )

    print()
    print("Results:")
    for name, status in results:
        print(f"  {name}: {status}")


def cmd_rebase(args: argparse.Namespace) -> None:
    branch = current_branch()
    target: str = args.target
    graph = discover()

    old_parent = graph.parent_of.get(branch)
    if not old_parent:
        old_parent = git("config", f"branch.{branch}.tree-parent", check=False)
    if not old_parent:
        raise TreeError(f"{branch} has no tree-parent configured.")

    if not git_ok("rev-parse", "--verify", old_parent):
        raise TreeError(f"Old parent {old_parent} does not exist.")

    fork_point = git("rev-parse", old_parent)
    commit_count = len(git_lines("rev-list", f"{fork_point}..{branch}"))

    descendants = graph.downstream_from(branch)

    siblings = [b for b, p in graph.parent_of.items() if p == old_parent and b != branch]

    print(f"Rebasing onto {target}:")
    print(f"  {branch}  [{commit_count} commits]  (old parent: {old_parent})")

    if descendants:
        print()
        print("Will propagate to:")
        subtree_lines = format_tree(graph, root=branch).splitlines()[1:]
        for line in subtree_lines:
            print(f"  {line}")

    if siblings:
        print()
        print(f"Warning: these branches also have {old_parent} as parent (will NOT be updated):")
        for s in siblings:
            print(f"  {s}")

    print()
    if args.dry or not confirm("Proceed?"):
        return

    auto_rerere = not getattr(args, "no_auto_rerere", False)

    main_stashed = False
    if bool(git("status", "--porcelain", check=False)):
        result = _run("git", "stash", check=False)
        main_stashed = "Saved working directory" in result.stdout

    _rebase_onto(
        branch, target, fork_point, cwd=None,
        auto_rerere=auto_rerere, stashed=False, main_stashed=main_stashed,
    )

    if main_stashed:
        if not git_ok("stash", "pop"):
            print(
                "Warning: could not pop main worktree stash — run `git stash pop` manually",
                file=sys.stderr,
            )

    git("config", f"branch.{branch}.tree-parent", target)
    print(f"Rebased {branch} onto {target}")

    if descendants:
        print()
        print("Cascading to descendants...")
        cmd_propagate(args)


def cmd_split(_args: argparse.Namespace) -> None:
    branch = current_branch()
    parent = git("config", f"branch.{branch}.tree-parent", check=False) or main_branch()

    fork_point = git("merge-base", parent, branch)
    commits = git_lines("log", "--oneline", "--reverse", f"{fork_point}..HEAD")

    if len(commits) < 2:
        raise TreeError("Need at least 2 commits to split.")

    selected = fzf_select(
        commits,
        prompt="Split after> ",
        header="Select the last commit for the new parent branch",
    )
    if not selected:
        raise SystemExit(1)

    commit_hash = selected[0].split()[0]

    try:
        parent_name = input("New parent branch name: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1)
    if not parent_name:
        raise SystemExit(1)

    try:
        worktree_path = input("Create worktree for parent? [path / N]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        worktree_path = ""

    git("branch", parent_name, commit_hash)
    git("config", f"branch.{parent_name}.tree-parent", parent)
    git("config", f"branch.{branch}.tree-parent", parent_name)

    remote = git("config", f"branch.{branch}.remote", check=False)
    if remote:
        git("config", f"branch.{parent_name}.remote", remote)

    if worktree_path and worktree_path.lower() != "n":
        git("worktree", "add", worktree_path, parent_name)
        print(f"Created worktree at {worktree_path}")

    split_commits = git_lines("log", "--oneline", f"{fork_point}..{commit_hash}")
    remaining = git_lines("log", "--oneline", f"{commit_hash}..HEAD")
    print("\nSplit complete:")
    print(f"  {parent_name} ({len(split_commits)} commits) → new parent branch")
    print(f"  {branch} ({len(remaining)} commits) → now child of {parent_name}")


def cmd_push(args: argparse.Namespace) -> None:
    branch = current_branch()
    graph = discover()

    descendants = graph.downstream_from(branch)
    push_set = [branch] + descendants

    stale: list[str] = []
    ahead: dict[str, int] = {}

    for b in push_set:
        parent = graph.parent_of.get(b)
        if parent and b != branch:
            merge_base = git("merge-base", parent, b)
            parent_tip = git("rev-parse", parent)
            if merge_base != parent_tip:
                stale.append(b)
                continue

        info = graph.branches.get(b)
        remote_name = (info.remote if info else None) or "origin"
        remote_ref = f"{remote_name}/{b}"

        if git_ok("rev-parse", "--verify", remote_ref):
            count = len(git_lines("rev-list", f"{remote_ref}..{b}"))
        else:
            base = git("merge-base", graph.parent_of.get(b, main_branch()), b)
            count = len(git_lines("rev-list", f"{base}..{b}"))
        ahead[b] = count

    pushable = [b for b in push_set if b not in stale]

    if not pushable:
        print("Nothing to push.")
        return

    print("Pushing (--force-with-lease):")
    for b in push_set:
        if b in stale:
            print(f"  {b}  (stale - run propagate first)")
        else:
            print(f"  {b}  [{ahead.get(b, 0)} ahead]")
    print()

    if args.dry or not confirm("Proceed?"):
        return

    results: list[tuple[str, str]] = []
    for b in pushable:
        info = graph.branches.get(b)
        remote_name = (info.remote if info else None) or "origin"

        ok = git_ok("push", "--force-with-lease", "-u", remote_name, b)
        results.append((b, "ok" if ok else "FAILED"))

    print()
    print("Results:")
    for name, status in results:
        print(f"  {name}: {status}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_ZSH_COMPLETION = """\
#compdef git-tree

_git-tree() {
    local -a subcmds
    subcmds=(
        'propagate:Propagate changes to all descendants'
        'rebase:Rebase current branch + descendants onto new base'
        'branch:Create a child branch'
        'attach:Attach current branch to tree'
        'detach:Remove a branch from tree'
        'split:Split current branch into parent + child'
        'push:Push current branch + descendants'
        'completions:Emit shell completion script'
    )

    if (( CURRENT == 2 )); then
        _describe 'subcommand' subcmds
        return
    fi

    case $words[2] in
        propagate)
            _arguments '--dry[Show what would be done]' '--no-auto-rerere[Disable auto-continue via rerere]' ':branch:__git_heads'
            ;;
        push)
            _arguments '--dry[Show what would be done]'
            ;;
        rebase)
            _arguments '--dry[Show what would be done]' '--no-auto-rerere[Disable auto-continue via rerere]' ':target:__git_heads'
            ;;
        branch)
            _arguments ':name:' '--path[Create worktree at this path]:path:_directories'
            ;;
        attach|detach)
            _arguments ':branch:__git_heads'
            ;;
        completions)
            _arguments ':shell:(zsh bash)'
            ;;
    esac
}

_git-tree "$@"
"""

_BASH_COMPLETION = """\
_git_tree() {
    local cur prev subcmds
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    subcmds="propagate rebase branch attach detach split push completions"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$subcmds" -- "$cur"))
        return
    fi

    case "${COMP_WORDS[1]}" in
        propagate)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "--dry --no-auto-rerere" -- "$cur"))
            else
                local branches=$(git for-each-ref --format='%(refname:short)' refs/heads/)
                COMPREPLY=($(compgen -W "$branches" -- "$cur"))
            fi
            ;;
        push)
            COMPREPLY=($(compgen -W "--dry" -- "$cur"))
            ;;
        rebase)
            if [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "--dry --no-auto-rerere" -- "$cur"))
            else
                local branches=$(git for-each-ref --format='%(refname:short)' refs/heads/)
                COMPREPLY=($(compgen -W "$branches" -- "$cur"))
            fi
            ;;
        branch)
            COMPREPLY=($(compgen -W "--path" -- "$cur"))
            ;;
        attach|detach)
            local branches=$(git for-each-ref --format='%(refname:short)' refs/heads/)
            COMPREPLY=($(compgen -W "$branches" -- "$cur"))
            ;;
        completions)
            COMPREPLY=($(compgen -W "zsh bash" -- "$cur"))
            ;;
    esac
}

complete -F _git_tree git-tree
"""


def cmd_completions(args: argparse.Namespace) -> None:
    if args.shell == "zsh":
        print(_ZSH_COMPLETION)
    else:
        print(_BASH_COMPLETION)


def _is_descendant_of(branch: str, ancestor: str, graph: Graph) -> bool:
    current = graph.parent_of.get(branch)
    visited: set[str] = set()
    while current:
        if current == ancestor:
            return True
        if current in visited:
            return False
        visited.add(current)
        current = graph.parent_of.get(current)
    return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="git-tree", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    propagate_p = sub.add_parser("propagate", help="Propagate changes to all descendants")
    propagate_p.add_argument("branch", nargs="?", help="Branch to propagate from (default: current)")
    propagate_p.add_argument("--dry", action="store_true", help="Show what would be done")
    propagate_p.add_argument(
        "--no-auto-rerere", action="store_true", help="Disable auto-continue via rerere"
    )

    rebase_p = sub.add_parser("rebase", help="Rebase current branch + descendants onto new base")
    rebase_p.add_argument("target", help="Branch or ref to rebase onto")
    rebase_p.add_argument("--dry", action="store_true", help="Show what would be done")
    rebase_p.add_argument(
        "--no-auto-rerere", action="store_true", help="Disable auto-continue via rerere"
    )

    branch_p = sub.add_parser("branch", help="Create a child branch")
    branch_p.add_argument("name", help="Name for the new branch")
    branch_p.add_argument("--path", help="Create worktree at this path")

    attach_p = sub.add_parser("attach", help="Attach current branch to tree")
    attach_p.add_argument("parent", nargs="?", help="Parent branch (fzf if omitted)")

    detach_p = sub.add_parser("detach", help="Remove a branch from tree")
    detach_p.add_argument("branch", nargs="?", help="Branch to detach (default: current)")

    sub.add_parser("split", help="Split current branch into parent + child")

    push_p = sub.add_parser("push", help="Push current branch + descendants")
    push_p.add_argument("--dry", action="store_true", help="Show what would be done")

    completions_p = sub.add_parser("completions", help="Emit shell completion script")
    completions_p.add_argument("shell", choices=["zsh", "bash"], help="Shell type")

    args = parser.parse_args()

    commands = {
        None: cmd_tree,
        "propagate": cmd_propagate,
        "rebase": cmd_rebase,
        "branch": cmd_branch,
        "attach": cmd_attach,
        "detach": cmd_detach,
        "split": cmd_split,
        "push": cmd_push,
        "completions": cmd_completions,
    }

    handler = commands.get(args.command, cmd_tree)
    handler(args)


if __name__ == "__main__":
    main()
