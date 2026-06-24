from __future__ import annotations

import pytest

from git_tree.cli import TreeError, discover, main

from .conftest import RepoHelper


class TestEdgeCases:
    def test_missing_parent_branch_excluded(self, repo: RepoHelper, capsys) -> None:
        repo.git("config", "branch.main.tree-parent-branch", "nonexistent")
        graph = discover()
        assert "main" not in graph.parent_of
        assert "main" not in graph.branches
        err = capsys.readouterr().err
        assert "nonexistent" in err

    def test_empty_graph(self, repo: RepoHelper) -> None:
        graph = discover()
        assert graph.parent_of == {}
        assert graph.children_of == {}


class TestGitFailureSurfacesCleanly:
    def test_outside_repo_reports_git_error_not_traceback(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        # Outside any git repo the first git() in discover() exits 128. main() must surface
        # git's own message as a clean error, not a raw CalledProcessError traceback.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # don't find a parent repo

        with pytest.raises(SystemExit):
            main(["remove", "whatever"])

        err = capsys.readouterr().err
        assert "git command failed" in err
        assert "git worktree list --porcelain" in err
        assert "fatal" in err  # git's own stderr is included


class TestCycles:
    def test_cycle_raises(self, repo: RepoHelper, capsys) -> None:
        repo.git("branch", "a")
        repo.git("branch", "b")
        repo.set_parent("a", "b")
        repo.set_parent("b", "a")

        with pytest.raises(TreeError):
            discover()
        assert "cycle" in capsys.readouterr().err

    def test_self_parent_raises(self, repo: RepoHelper, capsys) -> None:
        repo.git("branch", "a")
        repo.set_parent("a", "a")

        with pytest.raises(TreeError):
            discover()
        assert "cycle" in capsys.readouterr().err
