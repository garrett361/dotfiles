from __future__ import annotations

import pytest

from git_tree.cli import TreeError, discover

from .conftest import RepoHelper


class TestEdgeCases:
    def test_missing_parent_branch_excluded(self, repo: RepoHelper, capsys) -> None:
        repo.git("config", "branch.main.tree-parent", "nonexistent")
        graph = discover()
        assert "main" not in graph.parent_of
        assert "main" not in graph.branches
        err = capsys.readouterr().err
        assert "nonexistent" in err

    def test_empty_graph(self, repo: RepoHelper) -> None:
        graph = discover()
        assert graph.parent_of == {}
        assert graph.children_of == {}


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
