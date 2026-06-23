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

    def test_unpushed_root_reports_zero_ahead(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        # A standalone root (no tree-parent) never pushed: the ahead-count falls back to a
        # self-base (0) instead of anchoring on main, and the push still succeeds.
        repo.git("branch", "base")  # root: has a tree-child below but no tree-parent
        repo.branch("child", parent="base")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))
        (wt / "c1.txt").write_text("c1")
        repo.git("add", "c1.txt", cwd=wt)
        repo.git("commit", "-m", "child commit", cwd=wt)

        repo.checkout("base")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        out = capsys.readouterr().out
        assert "base  [0 ahead]" in out
        remote = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/base" in remote

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

    def test_failed_push_skips_descendants(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        repo.git("branch", "a", "main")
        repo.set_parent("a", "main")
        wt_a = repo.worktree("a", str(tmp_path / "wt-a"))
        (wt_a / "a1.txt").write_text("a1")
        repo.git("add", "a1.txt", cwd=wt_a)
        repo.git("commit", "-m", "a commit", cwd=wt_a)
        repo.git("branch", "b", "a")
        repo.set_parent("b", "a")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "b commit", cwd=wt_b)

        # Server-side hook rejects pushes to `a` only.
        hook = repo.origin / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\nwhile read old new ref; do\n"
            '  [ "$ref" = "refs/heads/a" ] && exit 1\ndone\nexit 0\n'
        )
        hook.chmod(0o755)

        monkeypatch.chdir(wt_a)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        out = capsys.readouterr().out
        assert "a: FAILED" in out
        assert "skipped" in out  # b not pushed because its base (a) failed

        remote = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/a" not in remote
        assert "refs/heads/b" not in remote

    def test_stale_branch_descendant_not_pushed(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        # main -> a -> b -> c; make `b` stale, so its descendant `c` is skipped.
        repo.git("branch", "a", "main")
        repo.set_parent("a", "main")
        wt_a = repo.worktree("a", str(tmp_path / "wt-a"))
        (wt_a / "a1.txt").write_text("a1")
        repo.git("add", "a1.txt", cwd=wt_a)
        repo.git("commit", "-m", "a commit", cwd=wt_a)
        repo.git("branch", "b", "a")
        repo.set_parent("b", "a")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "b commit", cwd=wt_b)
        repo.git("branch", "c", "b")
        repo.set_parent("c", "b")
        wt_c = repo.worktree("c", str(tmp_path / "wt-c"))
        (wt_c / "c1.txt").write_text("c1")
        repo.git("add", "c1.txt", cwd=wt_c)
        repo.git("commit", "-m", "c commit", cwd=wt_c)

        # Advance `a` past `b`'s fork so `b` is stale relative to `a`.
        (wt_a / "a2.txt").write_text("a2")
        repo.git("add", "a2.txt", cwd=wt_a)
        repo.git("commit", "-m", "advance a past b fork", cwd=wt_a)

        monkeypatch.chdir(wt_a)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        out = capsys.readouterr().out
        assert "stale" in out.lower()  # b
        assert "skipped" in out  # c: base (b) is stale, not on remote

        remote = repo.git("ls-remote", "--heads", str(repo.origin))
        assert "refs/heads/a" in remote  # a (top) still pushes
        assert "refs/heads/b" not in remote
        assert "refs/heads/c" not in remote

    def test_force_with_lease_blocks_clobber(self, repo: RepoHelper, monkeypatch, tmp_path) -> None:
        """A teammate commit on origin must not be clobbered: we intentionally do
        not fetch, so the lease rejects the force-push."""
        repo.branch("feature", parent="main")
        wt = repo.worktree("feature", str(tmp_path / "wt-feature"))
        (wt / "f1.txt").write_text("f1")
        repo.git("add", "f1.txt", cwd=wt)
        repo.git("commit", "-m", "first", cwd=wt)
        repo.push("feature")

        # Teammate advances origin/feature out-of-band.
        clone2 = tmp_path / "clone2"
        repo.git("clone", str(repo.origin), str(clone2), cwd=tmp_path)
        repo.git("config", "user.email", "t@t.com", cwd=clone2)
        repo.git("config", "user.name", "t", cwd=clone2)
        repo.git("checkout", "feature", cwd=clone2)
        (clone2 / "team.txt").write_text("team")
        repo.git("add", "team.txt", cwd=clone2)
        repo.git("commit", "-m", "teammate commit", cwd=clone2)
        repo.git("push", "origin", "feature", cwd=clone2)
        teammate_sha = repo.git("rev-parse", "feature", cwd=clone2)

        # Local diverges (does not contain the teammate commit).
        (wt / "f2.txt").write_text("f2")
        repo.git("add", "f2.txt", cwd=wt)
        repo.git("commit", "-m", "local second", cwd=wt)

        monkeypatch.chdir(wt)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_push(_ns())

        # The teammate commit must still be on origin (no clobber).
        remote_sha = repo.git("ls-remote", str(repo.origin), "refs/heads/feature").split()[0]
        assert remote_sha == teammate_sha

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
