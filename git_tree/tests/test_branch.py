from __future__ import annotations

import argparse

import pytest

from git_tree.cli import TreeError, cmd_branch, discover

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

    def test_worktree_add_failure_raises(self, repo: RepoHelper, capsys, tmp_path) -> None:
        # A path that already exists as a file makes `git worktree add` fail; cmd_branch
        # must surface that as a clear error and not register a half-created branch.
        bad_path = tmp_path / "exists"
        bad_path.write_text("not a directory")

        with pytest.raises(TreeError):
            cmd_branch(_ns(name="child", path=str(bad_path)))

        assert "failed to create worktree" in capsys.readouterr().err
        assert "child" not in discover().parent_of
