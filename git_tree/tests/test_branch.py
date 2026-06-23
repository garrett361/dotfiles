from __future__ import annotations

import argparse

from git_tree.cli import cmd_branch, discover

from .conftest import RepoHelper


def _ns(command: str = "branch", **kwargs: str) -> object:
    return argparse.Namespace(command=command, **kwargs)


class TestBranch:
    def test_creates_branch_with_parent_config(self, repo: RepoHelper, tmp_path) -> None:
        cmd_branch(_ns(name="child", path=str(tmp_path / "wt-child")))
        graph = discover()
        assert graph.parent_of["child"] == "main"

    def test_branch_starts_at_current_head(self, repo: RepoHelper, tmp_path) -> None:
        head_before = repo.head
        cmd_branch(_ns(name="child", path=str(tmp_path / "wt-child")))
        child_tip = repo.git("rev-parse", "child")
        assert child_tip == head_before

    def test_creates_worktree(self, repo: RepoHelper, tmp_path) -> None:
        wt_path = str(tmp_path / "wt-child")
        cmd_branch(_ns(name="child", path=wt_path))
        result = repo.git("worktree", "list", "--porcelain")
        assert "child" in result
