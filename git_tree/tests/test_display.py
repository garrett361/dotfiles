from __future__ import annotations

import argparse

from git_tree.cli import cmd_tree, discover, format_tree

from .conftest import RepoHelper


class TestFormatTree:
    def test_empty_tree(self, repo: RepoHelper) -> None:
        graph = discover()
        output = format_tree(graph)
        assert output == "main"

    def test_single_child(self, repo: RepoHelper) -> None:
        repo.branch("feature", parent="main")
        graph = discover()
        output = format_tree(graph)
        assert "└── feature" in output

    def test_multiple_children(self, repo: RepoHelper) -> None:
        repo.branch("a", parent="main")
        repo.branch("b", parent="main")
        graph = discover()
        output = format_tree(graph)
        lines = output.splitlines()
        assert lines[0] == "main"
        connectors = [line.strip()[:3] for line in lines[1:]]
        assert "├──" in connectors or "└──" in connectors

    def test_deep_chain(self, repo: RepoHelper) -> None:
        repo.branch("b", parent="main")
        repo.branch("c", parent="b")
        graph = discover()
        output = format_tree(graph)
        assert "main" in output
        assert "b" in output
        assert "c" in output

    def test_custom_root(self, repo: RepoHelper) -> None:
        repo.branch("b", parent="main")
        repo.branch("c", parent="b")
        graph = discover()
        output = format_tree(graph, root="b")
        lines = output.splitlines()
        assert lines[0] == "b"
        assert "c" in output

    def test_no_worktree_annotation(self, repo: RepoHelper) -> None:
        repo.branch("feature", parent="main")
        graph = discover()
        output = format_tree(graph)
        assert "(no worktree)" in output


class TestCmdTreeForest:
    def test_renders_roots_not_under_main(self, repo: RepoHelper, capsys) -> None:
        # A stack rooted at main, plus a separate forest whose base branch has no
        # tree-parent (so it isn't reachable from main).
        repo.branch("topic", parent="main")
        repo.git("branch", "standalone")  # real branch, not registered in the tree
        repo.branch("leaf", parent="standalone")

        cmd_tree(argparse.Namespace())
        out = capsys.readouterr().out

        assert "topic" in out
        # Previously invisible because the walk only descended from main.
        assert "standalone" in out
        assert "leaf" in out
