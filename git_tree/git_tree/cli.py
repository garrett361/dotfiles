"""git-tree: Cascading rebase tool for branch dependency chains."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(
    *args: str,
    check: bool = True,
    capture: bool = True,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
        cwd=cwd,
    )


def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> str:
    result = _run("git", *args, cwd=cwd, check=check)
    return result.stdout.strip()


def git_lines(*args: str, cwd: Path | str | None = None) -> list[str]:
    out = git(*args, cwd=cwd)
    return out.splitlines() if out else []


def git_ok(*args: str, cwd: Path | str | None = None) -> bool:
    result = _run("git", *args, check=False, cwd=cwd)
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
    return git("rev-parse", "--abbrev-ref", "HEAD")


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
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.split(" ", 1)[1])
        elif line.startswith("branch refs/heads/"):
            branch_name = line.removeprefix("branch refs/heads/")
            if current_path is not None:
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


def format_tree(graph: Graph, root: str | None = None) -> str:
    if root is None:
        root = main_branch()

    lines: list[str] = [root]
    children = graph.children_of.get(root, [])
    _format_subtree(graph, children, "", lines)
    return "\n".join(lines)


def _format_subtree(graph: Graph, children: list[str], prefix: str, lines: list[str]) -> None:
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

        lines.append(f"{prefix}{connector} {child}{annotation}")

        grandchildren = graph.children_of.get(child, [])
        if grandchildren:
            next_prefix = prefix + (BOX_SPACE if is_last else BOX_PIPE_SPACE)
            _format_subtree(graph, grandchildren, next_prefix, lines)


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
    print(format_tree(graph))


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
            print("No other branches available.", file=sys.stderr)
            sys.exit(1)
        selected = fzf_select(candidates, prompt="Select parent> ", header="Choose parent branch")
        if not selected:
            sys.exit(1)
        parent = selected[0]

    if not git_ok("merge-base", "--is-ancestor", parent, branch):
        merge_base = git("merge-base", parent, branch)
        parent_tip = git("rev-parse", parent)
        if merge_base != parent_tip:
            print(f"Warning: {branch} does not appear to descend from {parent}.", file=sys.stderr)

    git("config", f"branch.{branch}.tree-parent", parent)
    print(f"Attached {branch} to {parent}")


def cmd_detach(_args: argparse.Namespace) -> None:
    branch = current_branch()
    parent = git("config", f"branch.{branch}.tree-parent", check=False)
    if not parent:
        print(f"{branch} is not in the tree.", file=sys.stderr)
        sys.exit(1)

    git("config", "--unset", f"branch.{branch}.tree-parent")
    print(f"Detached {branch} (was child of {parent})")


def cmd_propagate(_args: argparse.Namespace) -> None:
    branch = current_branch()
    graph = discover()

    descendants = graph.downstream_from(branch)
    if not descendants:
        print("No descendants to propagate to.")
        return

    print(f"Propagating from {branch}:")
    subtree_lines = format_tree(graph, root=branch).splitlines()[1:]
    for line in subtree_lines:
        print(line)
    print()

    if not confirm("Proceed?"):
        return

    results: list[tuple[str, str]] = []
    skipped_subtrees: set[str] = set()

    for child in descendants:
        parent_of_child = graph.parent_of[child]

        if any(_is_descendant_of(child, s, graph) for s in skipped_subtrees):
            results.append((child, "skipped (ancestor failed)"))
            continue

        info = graph.branches.get(child)
        stashed = False

        if info and info.worktree and info.is_dirty:
            git("stash", cwd=info.worktree)
            stashed = True

        fork_point = git("merge-base", parent_of_child, child)

        rebase_ok = git_ok("rebase", "--onto", parent_of_child, fork_point, child)

        if not rebase_ok:
            git("rebase", "--abort", check=False)
            if stashed and info and info.worktree:
                git("stash", "pop", cwd=info.worktree, check=False)
            results.append((child, "CONFLICT"))
            skipped_subtrees.add(child)
            continue

        if stashed and info and info.worktree:
            pop_ok = git_ok("stash", "pop", cwd=info.worktree)
            if not pop_ok:
                results.append((child, "rebased (stash pop conflict - resolve manually)"))
                continue

        results.append((child, "ok"))

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
        print(f"{branch} has no tree-parent configured.", file=sys.stderr)
        sys.exit(1)

    if not git_ok("rev-parse", "--verify", old_parent):
        print(f"Old parent {old_parent} does not exist.", file=sys.stderr)
        sys.exit(1)

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
    if not confirm("Proceed?"):
        return

    rebase_ok = git_ok("rebase", "--onto", target, fork_point, branch)
    if not rebase_ok:
        git("rebase", "--abort", check=False)
        print(f"Rebase of {branch} onto {target} failed (conflict).", file=sys.stderr)
        sys.exit(1)

    git("config", f"branch.{branch}.tree-parent", target)
    print(f"Rebased {branch} onto {target}")

    if descendants:
        print()
        print("Cascading to descendants...")
        # Re-discover after rebase changed refs
        cmd_propagate(args)


def cmd_split(_args: argparse.Namespace) -> None:
    branch = current_branch()
    parent = git("config", f"branch.{branch}.tree-parent", check=False) or main_branch()

    fork_point = git("merge-base", parent, branch)
    commits = git_lines("log", "--oneline", "--reverse", f"{fork_point}..HEAD")

    if len(commits) < 2:
        print("Need at least 2 commits to split.", file=sys.stderr)
        sys.exit(1)

    selected = fzf_select(
        commits,
        prompt="Split after> ",
        header="Select the last commit for the new parent branch",
    )
    if not selected:
        sys.exit(1)

    commit_hash = selected[0].split()[0]

    try:
        parent_name = input("New parent branch name: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    if not parent_name:
        sys.exit(1)

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


def cmd_push(_args: argparse.Namespace) -> None:
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

    if not confirm("Proceed?"):
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

    sub.add_parser("propagate", help="Propagate changes to all descendants")

    rebase_p = sub.add_parser("rebase", help="Rebase current branch + descendants onto new base")
    rebase_p.add_argument("target", help="Branch or ref to rebase onto")

    branch_p = sub.add_parser("branch", help="Create a child branch")
    branch_p.add_argument("name", help="Name for the new branch")
    branch_p.add_argument("--path", help="Create worktree at this path")

    attach_p = sub.add_parser("attach", help="Attach current branch to tree")
    attach_p.add_argument("parent", nargs="?", help="Parent branch (fzf if omitted)")

    sub.add_parser("detach", help="Remove current branch from tree")

    sub.add_parser("split", help="Split current branch into parent + child")

    sub.add_parser("push", help="Push current branch + descendants")

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
    }

    handler = commands.get(args.command, cmd_tree)
    handler(args)


if __name__ == "__main__":
    main()
