from __future__ import annotations

import argparse

from git_tree.cli import cmd_push

from .conftest import RepoHelper


def _ns() -> object:
    return argparse.Namespace(dry=False)


class TestPush:
    def test_pushes_current_and_descendants(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("b1.txt", "b1", "b commit")
        repo.branch("c", parent="b")
        repo.checkout("c")
        repo.commit("c1.txt", "c1", "c commit")

        repo.checkout("b")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        remote_branches = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/b" in remote_branches
        assert "refs/heads/c" in remote_branches

    def test_uses_force_with_lease(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first")
        repo.push("feature")

        repo.commit("f2.txt", "f2", "second (will force)")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        remote_log = repo.git("log", "--oneline", "origin/feature")
        assert "second (will force)" in remote_log

    def test_stale_branch_skipped(self, repo: RepoHelper, monkeypatch, capsys) -> None:
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("b1.txt", "b1", "b commit")
        repo.branch("c", parent="b")
        repo.checkout("c")
        repo.commit("c1.txt", "c1", "c commit")

        # Advance b past c's fork point so c is stale relative to b
        repo.checkout("b")
        repo.commit("b2.txt", "b2", "advance b past c fork")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        out = capsys.readouterr().out
        assert "stale" in out.lower()

    def test_dry_does_not_push(self, repo: RepoHelper, capsys) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "feature commit")

        cmd_push(argparse.Namespace(dry=True))

        remote_branches = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/feature" not in remote_branches
        out = capsys.readouterr().out
        assert "Pushing" in out
