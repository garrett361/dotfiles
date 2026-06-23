"""git-tree: Cascading rebase tool for branch dependency chains."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import NoReturn


class TreeError(SystemExit):
    """Raised by helpers to exit with a user-facing message."""

    def __init__(self, msg: str):
        print(msg, file=sys.stderr)
        super().__init__(1)


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------


class Color(StrEnum):
    RED = "31"
    GREEN = "32"


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _color(text: str, code: Color) -> str:
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


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
# Fork point storage
# ---------------------------------------------------------------------------

# Each branch records the commit it forks from its parent in
# branch.<name>.tree-fork-commit. This is the parent's tip the branch was last
# rebased onto (or created/attached at), used as the `--onto <old-base>` exclude
# argument. It is the only reliable fork point once a parent moves ahead of its
# child: merge-base(parent, child) drifts backward in that case.


def _get_fork_commit(branch: str, parent: str, info: BranchInfo | None = None) -> str:
    """Stored fork commit; merge-base fallback for un-migrated/legacy branches."""
    if info is not None:
        stored = info.fork_commit
    else:
        stored = git("config", f"branch.{branch}.tree-fork-commit", check=False)
    if stored and git_ok("rev-parse", "--verify", stored):
        return stored
    return git("merge-base", parent, branch, check=False) or git("merge-base", parent, branch)


def _set_fork_commit(branch: str, commit: str) -> None:
    git("config", f"branch.{branch}.tree-fork-commit", commit)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BranchInfo:
    name: str
    worktree: Path | None = None
    remote: str | None = None
    fork_commit: str | None = None

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
    name = proc.stdout.strip()
    if name == "HEAD":
        # Detached HEAD: rev-parse --abbrev-ref prints the literal "HEAD".
        # Don't let callers operate on (or write config for) a branch named HEAD.
        raise TreeError("fatal: not on a branch (detached HEAD)")
    return name


def roots(graph: Graph) -> list[str]:
    """Every tree root: a tree-branch with children but no tracked parent."""
    return sorted(p for p in graph.children_of if p not in graph.parent_of)


def root_of(graph: Graph, branch: str) -> str:
    """Walk the (functional, acyclic) parent chain up to this branch's root.

    Returns `branch` unchanged when it has no parent — it is itself a root, or it is
    not registered in the tree at all (callers distinguish the two). `discover` rejects
    cycles, so the `seen` guard is purely defensive against a malformed graph.
    """
    seen: set[str] = set()
    while branch in graph.parent_of and branch not in seen:
        seen.add(branch)
        branch = graph.parent_of[branch]
    return branch


def _find_cycles(graph: Graph) -> list[list[str]]:
    """Return each parent-chain cycle (in loop order), or [] if the tree is acyclic.

    `tree-parent-branch` config is free-form, so a user can create a cycle
    (A→B→A) or self-parent (A→A). The parent graph is functional (one parent per
    node), so each weakly-connected component has at most one cycle and a simple
    walk finds it.
    """
    cycles: list[list[str]] = []
    seen: set[str] = set()
    for start in graph.parent_of:
        if start in seen:
            continue
        path: list[str] = []
        node = start
        while node in graph.parent_of and node not in seen:
            if node in path:
                cycles.append(path[path.index(node) :])
                break
            path.append(node)
            node = graph.parent_of[node]
        seen.update(path)
    return cycles


def discover() -> Graph:
    graph = Graph()

    worktree_map: dict[str, Path] = {}
    porcelain = git("worktree", "list", "--porcelain")
    current_path: Path | None = None
    worktree_count = 0
    detached_worktrees: list[Path] = []
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.split(" ", 1)[1])
            worktree_count += 1
        elif line.startswith("branch refs/heads/"):
            branch_name = line.removeprefix("branch refs/heads/")
            if current_path is not None:
                worktree_map[branch_name] = current_path
        elif line == "detached":
            if current_path is not None and worktree_count > 1:
                detached_worktrees.append(current_path)

    # Recover branch names for detached worktrees (mid-rebase)
    for wt_path in detached_worktrees:
        git_dir = git("rev-parse", "--git-dir", cwd=wt_path)
        git_dir_path = Path(git_dir) if Path(git_dir).is_absolute() else wt_path / git_dir
        head_name_file = git_dir_path / "rebase-merge" / "head-name"
        if not head_name_file.exists():
            head_name_file = git_dir_path / "rebase-apply" / "head-name"
        if head_name_file.exists():
            ref = head_name_file.read_text().strip()
            if ref.startswith("refs/heads/"):
                worktree_map[ref.removeprefix("refs/heads/")] = wt_path

    all_branches = git_lines("for-each-ref", "--format=%(refname:short)", "refs/heads/")
    all_branches_set = set(all_branches)

    orphaned: list[tuple[str, str]] = []
    for branch in all_branches:
        parent = git("config", f"branch.{branch}.tree-parent-branch", check=False)
        if not parent:
            # Legacy key (pre-rename); read-only fallback, no migration writes.
            parent = git("config", f"branch.{branch}.tree-parent", check=False)
        if not parent:
            continue

        if parent not in all_branches_set:
            orphaned.append((branch, parent))
            continue

        remote = git("config", f"branch.{branch}.remote", check=False) or None
        fork_commit = git("config", f"branch.{branch}.tree-fork-commit", check=False) or None
        info = BranchInfo(
            name=branch,
            worktree=worktree_map.get(branch),
            remote=remote,
            fork_commit=fork_commit,
        )
        graph.branches[branch] = info
        graph.parent_of[branch] = parent
        graph.children_of.setdefault(parent, []).append(branch)

    if orphaned:
        lines = [
            "Warning: these branches have a deleted parent "
            "(use `git tree attach` or `git tree detach`):"
        ]
        for b, p in orphaned:
            lines.append(f"  {b}  (parent was: {p})")
        print("\n".join(lines), file=sys.stderr)

    cycles = _find_cycles(graph)
    if cycles:
        lines = ["Branches form a dependency cycle (fix with `git tree attach`/`git tree detach`):"]
        for cycle in cycles:
            lines.append("  " + " → ".join(cycle + [cycle[0]]))
        raise TreeError("\n".join(lines))

    return graph


# ---------------------------------------------------------------------------
# Tree display
# ---------------------------------------------------------------------------

BOX_PIPE = "│"
BOX_TEE = "├──"
BOX_ELBOW = "└──"
BOX_SPACE = "   "
BOX_PIPE_SPACE = "│  "


def _git_status_summary(branch: str, info: BranchInfo) -> str:
    worktree = info.worktree
    if not worktree:
        return ""

    parts: list[str] = []

    out = git("status", "--porcelain", cwd=worktree)
    if out:
        staged = modified = untracked = conflicted = 0
        for line in out.splitlines():
            xy = line[:2]
            x, y = xy[0], xy[1]
            if "U" in xy or xy in ("DD", "AA"):
                conflicted += 1
            elif x in "MADRCT":  # include T (type-change), e.g. file <-> symlink
                staged += 1
            if y == "?":
                untracked += 1
            elif y not in (" ", "!", "U"):
                modified += 1
        if conflicted:
            parts.append(_color(f"✘{conflicted}", Color.RED))
        if staged:
            parts.append(_color(f"+{staged}", Color.GREEN))
        if modified:
            parts.append(_color(f"!{modified}", Color.RED))
        if untracked:
            parts.append(_color(f"?{untracked}", Color.RED))

    remote_name = info.remote or "origin"
    remote_ref = f"{remote_name}/{branch}"
    if git_ok("rev-parse", "--verify", remote_ref, cwd=worktree):
        ahead_behind = git(
            "rev-list",
            "--left-right",
            "--count",
            f"{branch}...{remote_ref}",
            cwd=worktree,
            check=False,
        )
        parts_ab = ahead_behind.split() if ahead_behind else []
        if len(parts_ab) == 2 and all(p.isdigit() for p in parts_ab):
            ahead, behind = parts_ab
            if int(ahead):
                parts.append(_color(f"⇡{ahead}", Color.GREEN))
            if int(behind):
                parts.append(_color(f"⇣{behind}", Color.RED))

    if not parts:
        return ""
    return "[" + "".join(parts) + "]"


def _pending_commit_count(parent: str, child: str, info: BranchInfo | None = None) -> int:
    """Count commits on parent that child hasn't incorporated yet.

    Counts from the stored fork point (where child currently sits on parent), so
    the number matches what propagate would actually replay; merge-base would
    over-count once parent and child have drifted.
    """
    base = _get_fork_commit(child, parent, info)
    if not base:
        return 0
    out = git("rev-list", "--count", f"{base}..{parent}", check=False)
    return int(out) if out else 0


def format_tree(
    graph: Graph,
    root: str,
    show_counts: bool = False,
    current: str | None = None,
) -> str:
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
    # The graph is acyclic: discover() raises on a cycle, so this recursion is bounded.
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        connector = BOX_ELBOW if is_last else BOX_TEE

        info = graph.branches.get(child)
        annotation = ""
        if info and info.worktree:
            wt = str(info.worktree).replace(str(Path.home()), "~")
            status = _git_status_summary(child, info)
            status_part = f"  {status}" if status else ""
            annotation = f"  {wt}{status_part}"
        elif info:
            annotation = "  (no worktree)"

        if show_counts:
            parent = graph.parent_of.get(child, "")
            if parent:
                n = _pending_commit_count(parent, child, info)
                if n > 0:
                    annotation += f"  [{n} new]"

        marker = "* " if current == child else ""
        lines.append(f"{prefix}{connector} {marker}{child}{annotation}")

        grandchildren = graph.children_of.get(child, [])
        if grandchildren:
            next_prefix = prefix + (BOX_SPACE if is_last else BOX_PIPE_SPACE)
            _format_subtree(
                graph,
                grandchildren,
                next_prefix,
                lines,
                show_counts=show_counts,
                current=current,
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

    # Render every root: a stack whose base isn't main/master (e.g. attached to a
    # feature branch) would otherwise be invisible. A root is a tree-branch that has
    # children but is not itself a tracked child.
    blocks = [format_tree(graph, root=r, current=current, show_counts=True) for r in roots(graph)]
    if blocks:
        print("\n\n".join(blocks))
    else:
        print("  (no tree-branches registered — use `git tree attach` or `git tree branch`)")


def cmd_branch(args: argparse.Namespace) -> None:
    parent = current_branch()
    name: str = args.name
    path: str = args.path

    git("worktree", "add", path, "-b", name)
    git("config", f"branch.{name}.tree-parent-branch", parent)
    _set_fork_commit(name, git("rev-parse", parent))

    remote = git("config", f"branch.{parent}.remote", check=False)
    if remote:
        git("config", f"branch.{name}.remote", remote)

    print(f"Created branch {name} with worktree at {path} (parent: {parent})")


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
        merge_base = git("merge-base", parent, branch, check=False)
        if not merge_base:
            raise TreeError(f"No common history between {parent} and {branch}.")
        parent_tip = git("rev-parse", parent)
        if merge_base != parent_tip:
            print(f"Warning: {branch} does not appear to descend from {parent}.", file=sys.stderr)

    git("config", f"branch.{branch}.tree-parent-branch", parent)
    _set_fork_commit(branch, git("merge-base", parent, branch))
    print(f"Attached {branch} to {parent}")


def cmd_detach(args: argparse.Namespace) -> None:
    branch = getattr(args, "branch", None) or current_branch()
    parent = git("config", f"branch.{branch}.tree-parent-branch", check=False) or git(
        "config", f"branch.{branch}.tree-parent", check=False
    )
    if not parent:
        raise TreeError(f"{branch} is not in the tree.")

    graph = discover()
    children = graph.children_of.get(branch, [])
    print(f"Detaching {branch} from {parent}.")
    if children:
        print(f"{branch} has children — they will form a separate tree:")
        print(format_tree(graph, root=branch))

    if not confirm("Proceed?"):
        return

    git("config", "--unset", f"branch.{branch}.tree-parent-branch", check=False)
    git("config", "--unset", f"branch.{branch}.tree-parent", check=False)
    git("config", "--unset", f"branch.{branch}.tree-fork-commit", check=False)
    print(f"Detached {branch} (was child of {parent})")

    if children:
        graph = discover()
        other_roots = [r for r in roots(graph) if r != branch]
        if other_roots:
            print("\nRemaining tree(s):")
            print("\n\n".join(format_tree(graph, root=r) for r in other_roots))


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


def _skip_empty_commits(child: str, parent: str, cwd: Path) -> str | None:
    """Loop --skip until rebase finishes or a real conflict appears. Returns None if
    a real conflict was hit (rebase left in progress for the user to resolve).

    Never aborts: a `--skip` that lands on a conflicting next commit is normal, so
    leave the rebase resumable rather than discarding it.
    """
    while _has_active_rebase(cwd):
        if git("ls-files", "--unmerged", cwd=cwd, check=False).strip():
            return None  # real conflict; leave rebase in progress
        if not git_ok("rebase", "--skip", cwd=cwd):
            return None  # --skip surfaced a conflict / can't proceed; hand to user
    return "ok (skipped empty)"


def _rebase_onto(
    child: str,
    parent: str,
    fork_point: str,
    cwd: Path,
    auto_rerere: bool,
    stashed: bool,
) -> str:
    """Attempt rebase of child onto parent in its worktree. Returns status or exits on conflict."""
    head_before = git("rev-parse", "HEAD", cwd=cwd)
    result = _run(
        "git",
        "rebase",
        "--no-reapply-cherry-picks",
        "--onto",
        parent,
        fork_point,
        cwd=cwd,
        check=False,
    )

    if result.returncode == 0:
        return "ok"

    if not _has_active_rebase(cwd):
        # Non-zero exit, no rebase left in progress. Confirm success positively:
        # the ref must have moved. Otherwise it's a real failure (bad ref,
        # pre-rebase hook reject, ...) — don't infer "ok" from stderr text.
        if git("rev-parse", "HEAD", cwd=cwd) != head_before:
            return "ok"
        stderr = result.stderr.strip() if result.stderr else ""
        raise TreeError(f"rebase of {child} onto {parent} failed:\n{stderr}")

    unmerged = git("ls-files", "--unmerged", cwd=cwd, check=False)
    if not unmerged.strip():
        status = _skip_empty_commits(child, parent, cwd)
        if status is not None:
            return status
        _conflict_exit(child, parent, cwd, stashed)

    if not auto_rerere:
        _conflict_exit(child, parent, cwd, stashed)

    while True:
        git("rerere", cwd=cwd, check=False)

        remaining = git("rerere", "remaining", cwd=cwd, check=False)
        if remaining.strip():
            _conflict_exit(child, parent, cwd, stashed)

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
            _conflict_exit(child, parent, cwd, stashed)


def _conflict_exit(child: str, parent: str, cwd: Path, stashed: bool) -> NoReturn:
    lines = [f"\nCONFLICT while rebasing {child} onto {parent}"]
    lines.append(f"Resolve conflicts in {cwd}, then run: git rebase --continue")
    if stashed:
        lines.append(f"Note: dirty worktree was stashed — run: cd {cwd} && git stash pop")
    raise TreeError("\n".join(lines))


def _require_worktrees(branches: list[str], graph: Graph) -> None:
    missing = [b for b in branches if not (graph.branches.get(b) and graph.branches[b].worktree)]
    if not missing:
        return
    lines = ["These branches need worktrees before this operation can proceed:"]
    for b in missing:
        lines.append(f"  {b}")
    lines.append("\nAdd worktrees with: git worktree add <path> <branch>")
    raise TreeError("\n".join(lines))


def _has_active_rebase(cwd: Path) -> bool:
    git_dir = git("rev-parse", "--git-dir", cwd=cwd)
    git_dir_path = Path(git_dir) if Path(git_dir).is_absolute() else cwd / git_dir
    return (git_dir_path / "rebase-merge").is_dir() or (git_dir_path / "rebase-apply").is_dir()


def _stash_push_if_created(cwd: Path) -> bool:
    """Stash tracked changes; return True iff a new stash entry was created.

    Detect via `refs/stash` advancing rather than parsing git's stdout, which is
    locale-dependent ("Saved working directory ..." is only English).
    """
    before = git("rev-parse", "--verify", "--quiet", "refs/stash", cwd=cwd, check=False)
    _run("git", "stash", "push", check=False, cwd=cwd)
    after = git("rev-parse", "--verify", "--quiet", "refs/stash", cwd=cwd, check=False)
    return bool(after) and after != before


def _require_clean_state(branches: list[str], graph: Graph) -> None:
    problems = []
    for b in branches:
        info = graph.branches.get(b)
        if not info or not info.worktree:
            continue
        wt = info.worktree
        out = git("status", "--porcelain", cwd=wt)
        if out and any("U" in line[:2] or line[:2] in ("DD", "AA") for line in out.splitlines()):
            problems.append((b, wt, "unresolved conflicts"))
        elif _has_active_rebase(wt):
            problems.append((b, wt, "rebase in progress"))
    if not problems:
        return
    lines = ["These branches are not in a clean state:"]
    for b, wt, reason in problems:
        lines.append(f"  {b}  ({reason} — resolve in: {wt})")
    raise TreeError("\n".join(lines))


@dataclass(frozen=True)
class RebaseResult:
    note: str  # how the rebase completed, for display: "ok", "ok (rerere)", ...
    pop_conflicted: bool = False


def _rebase_branch(
    branch: str,
    onto: str,
    fork_point: str,
    info: BranchInfo,
    *,
    auto_rerere: bool,
) -> RebaseResult:
    """Rebase `branch` onto `onto` in its worktree, stashing/popping dirty changes
    and recording the new fork point. Raises (via _rebase_onto) on a real conflict,
    leaving the rebase in progress. A pop conflict is non-fatal (the branch ref is
    already rebased); it's reported via `pop_conflicted` and the worktree is left
    for the user."""
    cwd = info.worktree
    assert cwd is not None  # callers guarantee a worktree via _require_worktrees
    stashed = info.is_dirty and _stash_push_if_created(cwd)
    note = _rebase_onto(branch, onto, fork_point, cwd, auto_rerere, stashed)
    # Rebase succeeded; record the fork before the pop (which only touches the
    # working tree). `rev-parse(onto)` is stable here — rebasing `branch` never
    # moves `onto`.
    _set_fork_commit(branch, git("rev-parse", onto))
    pop_conflicted = stashed and not git_ok("stash", "pop", cwd=cwd)
    return RebaseResult(note, pop_conflicted)


def _propagate_descendants(
    branch: str,
    graph: Graph,
    *,
    auto_rerere: bool = True,
) -> list[tuple[str, str]]:
    descendants = graph.downstream_from(branch)
    results: list[tuple[str, str]] = []

    for child in descendants:
        parent = graph.parent_of[child]
        info = graph.branches[child]
        fork_point = _get_fork_commit(child, parent, info)
        r = _rebase_branch(child, parent, fork_point, info, auto_rerere=auto_rerere)
        text = "rebased (stash pop conflict - resolve manually)" if r.pop_conflicted else r.note
        results.append((child, text))

    return results


def cmd_propagate(args: argparse.Namespace) -> None:
    branch = getattr(args, "branch", None) or current_branch()
    graph = discover()

    descendants = graph.downstream_from(branch)
    if not descendants:
        print("No descendants to propagate to.")
        return

    _require_worktrees(descendants, graph)
    _require_clean_state(descendants, graph)

    print(f"Propagating from {branch}:")
    subtree_lines = format_tree(graph, root=branch, show_counts=True).splitlines()[1:]
    for line in subtree_lines:
        print(line)
    print()

    if getattr(args, "dry", False) or not confirm("Proceed?"):
        return
    auto_rerere = not getattr(args, "no_auto_rerere", False)

    results = _propagate_descendants(branch, graph, auto_rerere=auto_rerere)

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
        old_parent = git("config", f"branch.{branch}.tree-parent-branch", check=False) or git(
            "config", f"branch.{branch}.tree-parent", check=False
        )
    if not old_parent:
        raise TreeError(f"{branch} has no tree-parent-branch configured.")

    if not git_ok("rev-parse", "--verify", old_parent):
        raise TreeError(f"Old parent {old_parent} does not exist.")

    fork_point = _get_fork_commit(branch, old_parent, graph.branches.get(branch))
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

    info = graph.branches.get(branch)
    if not info or not info.worktree:
        raise TreeError(
            f"{branch} needs a worktree. Add one with: git worktree add <path> {branch}"
        )
    _require_clean_state([branch], graph)
    if descendants:
        _require_worktrees(descendants, graph)
        _require_clean_state(descendants, graph)

    print()
    if args.dry or not confirm("Proceed?"):
        return

    auto_rerere = not getattr(args, "no_auto_rerere", False)

    r = _rebase_branch(branch, target, fork_point, info, auto_rerere=auto_rerere)
    git("config", f"branch.{branch}.tree-parent-branch", target)
    if r.pop_conflicted:
        print(
            f"Warning: could not pop worktree stash — run: cd {info.worktree} && git stash pop",
            file=sys.stderr,
        )
    print(f"Rebased {branch} onto {target}")

    if descendants:
        print()
        print("Cascading to descendants...")
        results = _propagate_descendants(branch, graph, auto_rerere=auto_rerere)
        print()
        print("Results:")
        for name, status in results:
            print(f"  {name}: {status}")


def cmd_split(_args: argparse.Namespace) -> None:
    branch = current_branch()
    parent = git("config", f"branch.{branch}.tree-parent-branch", check=False) or git(
        "config", f"branch.{branch}.tree-parent", check=False
    )

    # A child splits the commits above its fork from `parent`; that fork is inherited by
    # the new parent, which takes the child's old position. A root has no fork, so its
    # splittable range is its full history and the new parent it yields is itself a root.
    old_fork: str | None
    if parent:
        old_fork = _get_fork_commit(branch, parent)
        commits = git_lines("log", "--oneline", "--reverse", f"{old_fork}..HEAD")
    else:
        old_fork = None
        commits = git_lines("log", "--oneline", "--reverse", "HEAD")

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
        raise SystemExit(1) from None
    if not parent_name:
        raise SystemExit(1)

    try:
        worktree_path = input("Create worktree for parent? [path / N]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        worktree_path = ""

    git("branch", parent_name, commit_hash)
    git("config", f"branch.{branch}.tree-parent-branch", parent_name)
    _set_fork_commit(branch, git("rev-parse", commit_hash))
    if old_fork is not None:
        # Child split: the new parent inherits the child's former parent and fork point.
        # For a root split, the new parent is itself a root, so it gets neither.
        git("config", f"branch.{parent_name}.tree-parent-branch", parent)
        _set_fork_commit(parent_name, old_fork)

    remote = git("config", f"branch.{branch}.remote", check=False)
    if remote:
        git("config", f"branch.{parent_name}.remote", remote)

    if worktree_path and worktree_path.lower() != "n":
        # The split (branch + config) is already applied; a worktree-add failure
        # must not abort and leave the user unsure whether the split happened.
        if git_ok("worktree", "add", worktree_path, parent_name):
            print(f"Created worktree at {worktree_path}")
        else:
            print(
                f"Warning: could not create worktree at {worktree_path} "
                f"(the split itself succeeded; add one later with "
                f"`git worktree add <path> {parent_name}`).",
                file=sys.stderr,
            )

    split_range = f"{old_fork}..{commit_hash}" if old_fork is not None else commit_hash
    split_commits = git_lines("log", "--oneline", split_range)
    remaining = git_lines("log", "--oneline", f"{commit_hash}..HEAD")
    print("\nSplit complete:")
    print(f"  {parent_name} ({len(split_commits)} commits) → new parent branch")
    print(f"  {branch} ({len(remaining)} commits) → now child of {parent_name}")


def cmd_push(args: argparse.Namespace) -> None:
    branch = current_branch()
    graph = discover()

    descendants = graph.downstream_from(branch)
    push_set = [branch] + descendants
    _require_worktrees([b for b in push_set if b in graph.branches], graph)

    # Note: intentionally do NOT fetch here. `--force-with-lease` (no explicit
    # expected ref) compares the remote against the remote-tracking ref; fetching
    # first would advance that ref to a teammate's commit and let the force-push
    # silently clobber it. The un-fetched ref reflects our last known state and is
    # exactly what makes the lease reject a clobber.

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
            base = git("merge-base", graph.parent_of.get(b, b), b)
            count = len(git_lines("rev-list", f"{base}..{b}"))
        ahead[b] = count

    pushable = [b for b in push_set if b not in stale]

    # A branch whose ancestor in this run is stale can't be pushed — its base
    # wouldn't be on the remote. Propagate that through descendants (push_set is
    # topological, parents before children) for an accurate preview.
    blocked = set(stale)
    for b in pushable:
        if graph.parent_of.get(b) in blocked:
            blocked.add(b)

    if all(b in blocked for b in pushable):
        print("Nothing to push.")
        return

    print("Pushing (--force-with-lease):")
    for b in push_set:
        if b in stale:
            print(f"  {b}  (stale - run propagate first)")
        elif b in blocked:
            print(f"  {b}  (skipped - ancestor not pushed)")
        else:
            print(f"  {b}  [{ahead.get(b, 0)} ahead]")
    print()

    if args.dry or not confirm("Proceed?"):
        return

    results: list[tuple[str, str]] = []
    for b in pushable:
        # Skip if an ancestor in this run is stale or its push failed. Re-add b so
        # the block cascades to its own descendants later in the loop.
        if graph.parent_of.get(b) in blocked:
            results.append((b, "skipped (ancestor not pushed)"))
            blocked.add(b)
            continue
        info = graph.branches.get(b)
        remote_name = (info.remote if info else None) or "origin"

        ok = git_ok("push", "--force-with-lease", "-u", remote_name, b)
        if not ok:
            blocked.add(b)
        results.append((b, "ok" if ok else "FAILED"))

    print()
    print("Results:")
    for name, status in results:
        print(f"  {name}: {status}")


def cmd_log(args: argparse.Namespace) -> None:
    graph = discover()
    try:
        branch = current_branch()
    except TreeError:
        print("Not on a tree-branch.")
        raise SystemExit(0) from None
    # A branch participates in the forest if it has a parent (a tracked child) or has
    # children (a root). Anything else is a plain git branch git-tree doesn't track.
    if branch not in graph.parent_of and branch not in graph.children_of:
        print("Not on a tree-branch.")
        raise SystemExit(0)

    root = root_of(graph, branch)
    descendants = graph.downstream_from(root)
    all_refs = [root] + descendants

    cmd = ["git", "log", "--graph", "--oneline", "--decorate"]
    if _use_color():
        cmd.append("--color=always")
    cmd += all_refs

    boundary = git("merge-base", "--octopus", *all_refs, check=False)
    if boundary and git_ok("rev-parse", "--verify", f"{boundary}^"):
        cmd.append(f"^{boundary}^")

    cmd += args.extra
    result = subprocess.run(cmd)
    raise SystemExit(result.returncode)


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
        'log:Show git log graph for all tree-branches'
        'completions:Emit shell completion script'
    )

    if (( CURRENT == 2 )); then
        _describe 'subcommand' subcmds
        return
    fi

    case $words[2] in
        propagate)
            _arguments \
                '--dry[Show what would be done]' \
                '--no-auto-rerere[Disable auto-continue via rerere]' \
                ':branch:__git_heads'
            ;;
        push)
            _arguments '--dry[Show what would be done]'
            ;;
        rebase)
            _arguments \
                '--dry[Show what would be done]' \
                '--no-auto-rerere[Disable auto-continue via rerere]' \
                ':target:__git_heads'
            ;;
        branch)
            _arguments ':name:' ':path:_directories'
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
    subcmds="propagate rebase branch attach detach split push log completions"

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
            COMPREPLY=($(compgen -d -- "$cur"))
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:  # explicit argv for tests
    parser = argparse.ArgumentParser(prog="git-tree", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    propagate_p = sub.add_parser("propagate", help="Propagate changes to all descendants")
    propagate_p.add_argument(
        "branch", nargs="?", help="Branch to propagate from (default: current)"
    )
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
    branch_p.add_argument("path", help="Worktree path for the new branch")

    attach_p = sub.add_parser("attach", help="Attach current branch to tree")
    attach_p.add_argument("parent", nargs="?", help="Parent branch (fzf if omitted)")

    detach_p = sub.add_parser("detach", help="Remove a branch from tree")
    detach_p.add_argument("branch", nargs="?", help="Branch to detach (default: current)")

    sub.add_parser("split", help="Split current branch into parent + child")

    push_p = sub.add_parser("push", help="Push current branch + descendants")
    push_p.add_argument("--dry", action="store_true", help="Show what would be done")

    sub.add_parser("log", help="Show git log graph for all tree-branches")

    completions_p = sub.add_parser("completions", help="Emit shell completion script")
    completions_p.add_argument("shell", choices=["zsh", "bash"], help="Shell type")

    args, unknown = parser.parse_known_args(argv)
    if unknown and getattr(args, "command", None) != "log":
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    if getattr(args, "command", None) == "log":
        args.extra = unknown

    commands = {
        None: cmd_tree,
        "propagate": cmd_propagate,
        "rebase": cmd_rebase,
        "branch": cmd_branch,
        "attach": cmd_attach,
        "detach": cmd_detach,
        "split": cmd_split,
        "push": cmd_push,
        "log": cmd_log,
        "completions": cmd_completions,
    }

    handler = commands.get(args.command, cmd_tree)
    handler(args)


if __name__ == "__main__":
    main()
