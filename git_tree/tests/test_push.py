from __future__ import annotations

import argparse

from git_tree.cli import cmd_push

from .conftest import RepoHelper


def _ns() -> object:
    return argparse.Namespace(dry=False)


class TestPush:
    def test_pushes_current_and_descendants(self, repo: RepoHelper, monkeypatch, tmp_path) -> None:
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "b commit", cwd=wt_b)
        # Create c AFTER b's commit so c's fork point includes b's tip
        repo.git("branch", "c", cwd=wt_b)
        repo.set_parent("c", "b")
        wt_c = repo.worktree("c", str(tmp_path / "wt-c"))
        (wt_c / "c1.txt").write_text("c1")
        repo.git("add", "c1.txt", cwd=wt_c)
        repo.git("commit", "-m", "c commit", cwd=wt_c)

        monkeypatch.chdir(wt_b)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        remote_branches = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/b" in remote_branches
        assert "refs/heads/c" in remote_branches

    def test_uses_force_with_lease(self, repo: RepoHelper, monkeypatch, tmp_path) -> None:
        repo.branch("feature", parent="main")
        wt = repo.worktree("feature", str(tmp_path / "wt-feature"))
        (wt / "f1.txt").write_text("f1")
        repo.git("add", "f1.txt", cwd=wt)
        repo.git("commit", "-m", "first", cwd=wt)
        repo.push("feature")

        (wt / "f2.txt").write_text("f2")
        repo.git("add", "f2.txt", cwd=wt)
        repo.git("commit", "-m", "second (will force)", cwd=wt)

        monkeypatch.chdir(wt)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        remote_log = repo.git("log", "--oneline", "origin/feature")
        assert "second (will force)" in remote_log

    def test_stale_branch_skipped(self, repo: RepoHelper, monkeypatch, capsys, tmp_path) -> None:
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "b commit", cwd=wt_b)
        repo.branch("c", parent="b")
        wt_c = repo.worktree("c", str(tmp_path / "wt-c"))
        (wt_c / "c1.txt").write_text("c1")
        repo.git("add", "c1.txt", cwd=wt_c)
        repo.git("commit", "-m", "c commit", cwd=wt_c)

        # Advance b past c's fork point so c is stale relative to b
        (wt_b / "b2.txt").write_text("b2")
        repo.git("add", "b2.txt", cwd=wt_b)
        repo.git("commit", "-m", "advance b past c fork", cwd=wt_b)

        monkeypatch.chdir(wt_b)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        out = capsys.readouterr().out
        assert "stale" in out.lower()

    def test_dry_does_not_push(self, repo: RepoHelper, capsys, tmp_path, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        wt = repo.worktree("feature", str(tmp_path / "wt-feature"))
        (wt / "f1.txt").write_text("f1")
        repo.git("add", "f1.txt", cwd=wt)
        repo.git("commit", "-m", "feature commit", cwd=wt)

        monkeypatch.chdir(wt)
        cmd_push(argparse.Namespace(dry=True))

        remote_branches = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/feature" not in remote_branches
        out = capsys.readouterr().out
        assert "Pushing" in out
