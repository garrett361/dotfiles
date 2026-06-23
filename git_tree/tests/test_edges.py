from __future__ import annotations

from git_tree.cli import Graph, discover, format_tree

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
    def test_cycle_broken_and_warned(self, repo: RepoHelper, capsys) -> None:
        repo.git("branch", "a")
        repo.git("branch", "b")
        repo.set_parent("a", "b")
        repo.set_parent("b", "a")

        graph = discover()

        err = capsys.readouterr().err
        assert "dependency cycle" in err

        # The in-memory graph is acyclic: no branch is its own descendant, and
        # following parent_of from any node terminates.
        for branch in ("a", "b"):
            assert branch not in graph.downstream_from(branch)
        # Rendering from any node is finite (would recurse forever unguarded).
        assert format_tree(graph, root="a")
        assert format_tree(graph, root="b")

    def test_self_parent_broken(self, repo: RepoHelper, capsys) -> None:
        repo.git("branch", "a")
        repo.set_parent("a", "a")

        graph = discover()

        err = capsys.readouterr().err
        assert "dependency cycle" in err
        assert graph.parent_of.get("a") != "a"
        assert "a" not in graph.downstream_from("a")

    def test_format_subtree_cycle_guard(self) -> None:
        # A cyclic Graph built directly (bypassing discover's break). Empty
        # branches so format_tree makes no git calls. Without the guard this
        # recurses until RecursionError.
        graph = Graph(
            parent_of={"a": "b", "b": "a"},
            children_of={"a": ["b"], "b": ["a"]},
            branches={},
        )
        out = format_tree(graph, root="a")
        assert "(cycle)" in out
        assert out.count("\n") < 10  # finite, not blown up
