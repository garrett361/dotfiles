from __future__ import annotations

import subprocess

from git_tree.cli import cmd_branch, discover

from .conftest import RepoHelper


def _ns(command: str = "branch", **kwargs: str) -> object:
    import argparse

    ns = argparse.Namespace(command=command, **kwargs)
    return ns


class TestBranch:
    def test_creates_branch_with_parent_config(self, repo: RepoHelper) -> None:
        cmd_branch(_ns(name="child", path=None))
        graph = discover()
        assert graph.parent_of["child"] == "main"

    def test_branch_starts_at_current_head(self, repo: RepoHelper) -> None:
        head_before = repo.head
        cmd_branch(_ns(name="child", path=None))
        child_tip = repo.git("rev-parse", "child")
        assert child_tip == head_before

    def test_creates_worktree_when_path_given(self, repo: RepoHelper, tmp_path) -> None:
        wt_path = str(tmp_path / "wt-child")
        cmd_branch(_ns(name="child", path=wt_path))
        result = repo.git("worktree", "list", "--porcelain")
        assert "child" in result

    def test_inherits_remote(self, repo: RepoHelper) -> None:
        repo.git("config", "branch.main.remote", "origin")
        cmd_branch(_ns(name="child", path=None))
        remote = repo.git("config", "branch.child.remote", check=False)
        assert remote == "origin"

    def test_no_remote_inheritance_when_parent_has_none(self, repo: RepoHelper) -> None:
        repo.git("config", "--unset", "branch.main.remote", check=False)
        cmd_branch(_ns(name="child", path=None))
        result = subprocess.run(
            ["git", "config", "branch.child.remote"],
            cwd=repo.work,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
