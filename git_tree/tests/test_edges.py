from __future__ import annotations

from git_tree.cli import discover

from .conftest import RepoHelper


class TestEdgeCases:
    def test_missing_parent_branch_excluded(self, repo: RepoHelper, capsys) -> None:
        repo.git("config", "branch.main.tree-parent", "nonexistent")
        graph = discover()
        assert "main" not in graph.parent_of
        assert "main" not in graph.branches
        err = capsys.readouterr().err
        assert "nonexistent" in err

    def test_circular_dependency_no_infinite_loop(self, repo: RepoHelper) -> None:
        repo.git("branch", "a")
        repo.git("branch", "b")
        repo.set_parent("a", "b")
        repo.set_parent("b", "a")
        graph = discover()
        desc = graph.downstream_from("a")
        assert "b" in desc
        assert len(desc) <= 2

    def test_empty_graph(self, repo: RepoHelper) -> None:
        graph = discover()
        assert graph.parent_of == {}
        assert graph.children_of == {}
