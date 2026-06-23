from __future__ import annotations

import argparse
import subprocess

import pytest

from git_tree.cli import TreeError, cmd_attach, cmd_detach, discover, roots

from .conftest import RepoHelper, _git


def _ns(**kwargs) -> object:
    return argparse.Namespace(**kwargs)


class TestAttach:
    def test_sets_tree_parent(self, repo: RepoHelper) -> None:
        repo.git("branch", "feature")
        repo.checkout("feature")
        cmd_attach(_ns(parent="main"))
        graph = discover()
        assert graph.parent_of["feature"] == "main"

    def test_overwrites_existing_parent(self, repo: RepoHelper) -> None:
        repo.git("branch", "feature")
        repo.git("branch", "other")
        repo.set_parent("feature", "main")
        repo.checkout("feature")
        cmd_attach(_ns(parent="other"))
        graph = discover()
        assert graph.parent_of["feature"] == "other"

    def test_warns_when_not_ancestor(self, repo: RepoHelper, capsys) -> None:
        repo.git("branch", "unrelated")
        repo.checkout("unrelated")
        repo.commit("u1.txt", "u1", "diverge from main")

        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance main")

        repo.checkout("unrelated")
        cmd_attach(_ns(parent="main"))

        graph = discover()
        assert graph.parent_of["unrelated"] == "main"
        err = capsys.readouterr().err
        assert "Warning" in err or "does not appear to descend" in err

    def test_attach_disjoint_history_clean_error(self, repo: RepoHelper, capsys, tmp_path) -> None:
        """Attaching to a branch with no common history is a TreeError, not a traceback."""
        orphan_wt = tmp_path / "orphan-wt"
        repo.git("worktree", "add", "--detach", str(orphan_wt))
        _git("checkout", "--orphan", "orphan", cwd=orphan_wt)
        (orphan_wt / "o.txt").write_text("orphan")
        _git("add", "o.txt", cwd=orphan_wt)
        _git("commit", "-m", "orphan root", cwd=orphan_wt)
        repo.git("worktree", "remove", str(orphan_wt))

        repo.checkout("orphan")
        with pytest.raises(TreeError):
            cmd_attach(_ns(parent="main"))

        err = capsys.readouterr().err
        assert "No common history" in err


class TestDetach:
    def _branch_config(self, repo: RepoHelper, branch: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "config", f"branch.{branch}.tree-parent-branch"],
            cwd=repo.work,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_removes_tree_parent(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_detach(_ns())
        assert self._branch_config(repo, "feature").returncode != 0

    def test_detach_by_name_from_different_branch(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("main")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_detach(_ns(branch="feature"))
        assert self._branch_config(repo, "feature").returncode != 0

    def test_declined_confirmation_keeps_parent(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_detach(_ns())
        # Config untouched: still attached to main.
        result = self._branch_config(repo, "feature")
        assert result.returncode == 0
        assert result.stdout.strip() == "main"

    def test_detach_with_children_lists_remaining_trees(
        self, repo: RepoHelper, capsys, monkeypatch
    ) -> None:
        # mid is a tree-child of main and parent of leaf. Detaching mid splits the forest:
        # mid+leaf become their own tree, and main's tree (now without mid) is "remaining".
        repo.branch("topic", parent="main")
        repo.branch("mid", parent="main")
        repo.branch("leaf", parent="mid")
        repo.checkout("mid")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_detach(_ns())

        # Forest actually split: mid is now a root carrying leaf; main keeps topic.
        graph = discover()
        assert "mid" not in graph.parent_of
        assert graph.parent_of["leaf"] == "mid"
        assert graph.parent_of["topic"] == "main"
        assert roots(graph) == ["main", "mid"]

        out = capsys.readouterr().out
        assert "they will form a separate tree" in out
        assert "leaf" in out
        assert "Remaining tree(s):" in out
        assert "topic" in out  # still under main

    def test_detach_not_in_tree_exits(self, repo: RepoHelper) -> None:
        repo.git("branch", "orphan")
        repo.checkout("orphan")

        with pytest.raises(SystemExit):
            cmd_detach(_ns())
