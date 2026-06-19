from __future__ import annotations

from git_tree.cli import cmd_rebase, discover

from .conftest import RepoHelper


def _ns(target: str) -> object:
    import argparse

    return argparse.Namespace(command="rebase", target=target)


class TestRebase:
    def test_rebases_onto_target(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "feature commit")

        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance main")

        repo.checkout("feature")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_rebase(_ns(target="main"))

        log = repo.git("log", "--oneline", "feature")
        assert "advance main" in log
        assert "feature commit" in log

    def test_updates_tree_parent_config(self, repo: RepoHelper, monkeypatch) -> None:
        repo.git("branch", "base")
        repo.set_parent("base", "main")
        repo.branch("child", parent="base")
        repo.checkout("child")
        repo.commit("c1.txt", "c1", "child commit")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_rebase(_ns(target="main"))

        graph = discover()
        assert graph.parent_of["child"] == "main"

    def test_cascades_to_descendants(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("b1.txt", "b1", "b commit")
        repo.branch("c", parent="b")
        repo.checkout("c")
        repo.commit("c1.txt", "c1", "c commit")

        repo.checkout("main")
        repo.commit("m2.txt", "m2", "new main commit")

        repo.checkout("b")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_rebase(_ns(target="main"))

        c_log = repo.git("log", "--oneline", "c")
        assert "new main commit" in c_log
        assert "c commit" in c_log

    def test_excludes_old_parent_commits(self, repo: RepoHelper, monkeypatch) -> None:
        """After squash-merge, rebase replays only child's unique commits, not parent's."""
        # Build parent-branch with 2 commits on top of main
        repo.branch("parent-branch", parent="main")
        repo.checkout("parent-branch")
        repo.commit("p1.txt", "p1", "parent commit 1")
        repo.commit("p2.txt", "p2", "parent commit 2")

        # child-branch adds its own commit on top of parent-branch
        repo.branch("child-branch", parent="parent-branch")
        repo.checkout("child-branch")
        repo.commit("c1.txt", "c1", "child unique commit")

        # child-branch's log now includes parent's commits in its history
        child_log_before = repo.git("log", "--oneline", "child-branch")
        assert "parent commit 1" in child_log_before
        assert "parent commit 2" in child_log_before

        # Simulate squash-merge of parent-branch into main
        repo.checkout("main")
        repo.git("merge", "--squash", "parent-branch")
        repo.git("commit", "-m", "squash merge of parent-branch")

        # Rebase child onto main — the old parent branch still exists locally
        # (user rebases before pruning the merged branch)
        repo.checkout("child-branch")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_rebase(_ns(target="main"))

        log = repo.git("log", "--oneline", "child-branch")
        assert "child unique commit" in log
        assert "squash merge" in log
        # Parent's original commits must NOT be replayed as separate commits
        assert "parent commit 1" not in log
        assert "parent commit 2" not in log

    def test_confirmation_decline_aborts(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "feature commit")
        head_before = repo.head

        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_rebase(_ns(target="main"))

        assert repo.head == head_before

    def test_conflict_aborts(self, repo: RepoHelper, monkeypatch) -> None:
        repo.commit("shared.txt", "original", "base")
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("shared.txt", "feature version", "feature modifies shared")

        repo.checkout("main")
        repo.commit("shared.txt", "main version", "main modifies shared")

        repo.checkout("feature")
        monkeypatch.setattr("builtins.input", lambda _: "y")

        import pytest

        with pytest.raises(SystemExit):
            cmd_rebase(_ns(target="main"))
