from __future__ import annotations

import argparse

import pytest

from git_tree.cli import cmd_propagate

from .conftest import RepoHelper


def _ns(
    *, dry: bool = False, no_auto_rerere: bool = False, branch: str | None = None
) -> object:
    return argparse.Namespace(dry=dry, no_auto_rerere=no_auto_rerere, branch=branch)


class TestPropagate:
    def test_linear_cascade(self, repo: RepoHelper, monkeypatch, tmp_path) -> None:
        repo.commit("a1.txt", "a1", "commit on main for b")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "commit on b", cwd=wt_b)
        repo.branch("c", parent="b")
        wt_c = repo.worktree("c", str(tmp_path / "wt-c"))
        (wt_c / "c1.txt").write_text("c1")
        repo.git("add", "c1.txt", cwd=wt_c)
        repo.git("commit", "-m", "commit on c", cwd=wt_c)

        repo.checkout("main")
        repo.commit("a2.txt", "a2", "new commit on main")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        b_contains = repo.git("log", "--oneline", "b")
        assert "new commit on main" in b_contains

        c_contains = repo.git("log", "--oneline", "c")
        assert "new commit on main" in c_contains
        assert "commit on b" in c_contains

    def test_no_descendants_is_noop(self, repo: RepoHelper, monkeypatch, capsys, tmp_path) -> None:
        repo.branch("leaf", parent="main")
        repo.worktree("leaf", str(tmp_path / "wt-leaf"))
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns(branch="leaf"))
        out = capsys.readouterr().out
        assert "No descendants" in out

    def test_conflict_stops_and_exits(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        repo.commit("shared.txt", "original", "base")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "shared.txt").write_text("from b")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("commit", "-m", "b modifies shared", cwd=wt_b)

        repo.checkout("main")
        repo.commit("shared.txt", "from main", "main modifies shared (conflict)")

        monkeypatch.setattr("builtins.input", lambda _: "y")

        with pytest.raises(SystemExit):
            cmd_propagate(_ns())

        err = capsys.readouterr().err
        assert "CONFLICT" in err

    def test_already_up_to_date(self, repo: RepoHelper, monkeypatch, capsys, tmp_path) -> None:
        repo.branch("b", parent="main")
        repo.worktree("b", str(tmp_path / "wt-b"))
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())
        out = capsys.readouterr().out
        assert "b" in out

    def test_child_no_unique_commits(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        """Branch with no unique commits beyond parent still propagates cleanly."""
        repo.branch("b", parent="main")
        repo.worktree("b", str(tmp_path / "wt-b"))
        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance main past b fork")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        b_log = repo.git("log", "--oneline", "b")
        assert "advance main past b fork" in b_log

    def test_grandchild_no_unique_commits_cascades(
        self, repo: RepoHelper, monkeypatch, tmp_path
    ) -> None:
        repo.branch("b", parent="main")
        repo.worktree("b", str(tmp_path / "wt-b"))
        repo.branch("c", parent="b")
        repo.worktree("c", str(tmp_path / "wt-c"))
        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance main")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        b_log = repo.git("log", "--oneline", "b")
        assert "advance main" in b_log
        c_log = repo.git("log", "--oneline", "c")
        assert "advance main" in c_log

    def test_confirmation_decline_is_noop(
        self, repo: RepoHelper, monkeypatch, tmp_path
    ) -> None:
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "on b", cwd=wt_b)
        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance main")

        b_tip_before = repo.git("rev-parse", "b")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_propagate(_ns())

        assert repo.git("rev-parse", "b") == b_tip_before

    def test_dirty_worktree_stash_roundtrip(self, repo: RepoHelper, monkeypatch, tmp_path) -> None:
        repo.commit("a1.txt", "a1", "base for b")
        repo.branch("b", parent="main")
        wt_path = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_path / "uncommitted.txt").write_text("dirty content")

        repo.checkout("main")
        repo.commit("a2.txt", "a2", "new on main")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        assert (wt_path / "uncommitted.txt").exists()
        assert (wt_path / "uncommitted.txt").read_text() == "dirty content"

    def test_dry_does_not_modify(self, repo: RepoHelper, capsys, tmp_path) -> None:
        repo.commit("a1.txt", "a1", "base for b")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "on b", cwd=wt_b)
        repo.checkout("main")
        repo.commit("a2.txt", "a2", "advance main")

        b_tip_before = repo.git("rev-parse", "b")
        cmd_propagate(_ns(dry=True))

        assert repo.git("rev-parse", "b") == b_tip_before
        out = capsys.readouterr().out
        assert "Propagating from" in out

    def test_preview_shows_pending_commit_counts(self, repo: RepoHelper, capsys, tmp_path) -> None:
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "on b", cwd=wt_b)
        repo.checkout("main")
        repo.commit("m2.txt", "m2", "first new on main")
        repo.commit("m3.txt", "m3", "second new on main")

        cmd_propagate(_ns(dry=True))

        out = capsys.readouterr().out
        assert "[2 new]" in out

    def test_preview_no_count_when_up_to_date(self, repo: RepoHelper, capsys, tmp_path) -> None:
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "on b", cwd=wt_b)

        repo.checkout("main")
        cmd_propagate(_ns(dry=True))

        out = capsys.readouterr().out
        assert "[" not in out


class TestPropagateRerere:
    def test_auto_rerere_continues_through_known_conflict(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        repo.enable_rerere()
        repo.commit("shared.txt", "original", "base")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "shared.txt").write_text("from b")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("commit", "-m", "b modifies shared", cwd=wt_b)
        b_original = repo.git("rev-parse", "b")

        repo.checkout("main")
        repo.commit("shared.txt", "from main", "main modifies shared")

        # Record rerere resolution in b's worktree
        repo.git("rebase", "--onto", "main", b_original + "~1", cwd=wt_b, check=False)
        (wt_b / "shared.txt").write_text("resolved content")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("rebase", "--continue", cwd=wt_b)

        # Reset b back to original state
        repo.git("reset", "--hard", b_original, cwd=wt_b)

        # Now propagate — rerere should auto-resolve
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        out = capsys.readouterr().out
        assert "rerere" in out
        b_log = repo.git("log", "--oneline", "b")
        assert "main modifies shared" in b_log

    def test_auto_rerere_stops_on_unknown_conflict(
        self, repo: RepoHelper, monkeypatch, tmp_path
    ) -> None:
        repo.enable_rerere()
        repo.commit("shared.txt", "original", "base")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "shared.txt").write_text("from b")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("commit", "-m", "b modifies shared", cwd=wt_b)
        b_original = repo.git("rev-parse", "b")

        repo.checkout("main")
        repo.commit("shared.txt", "from main", "main modifies shared")

        # No rerere recording — propagate should still stop
        monkeypatch.setattr("builtins.input", lambda _: "y")

        with pytest.raises(SystemExit):
            cmd_propagate(_ns())

        assert repo.git("rev-parse", "b") == b_original

    def test_auto_rerere_disabled_with_flag(
        self, repo: RepoHelper, monkeypatch, tmp_path
    ) -> None:
        repo.enable_rerere()
        repo.commit("shared.txt", "original", "base")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "shared.txt").write_text("from b")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("commit", "-m", "b modifies shared", cwd=wt_b)
        b_original = repo.git("rev-parse", "b")

        repo.checkout("main")
        repo.commit("shared.txt", "from main", "main modifies shared")

        # Even though rerere is enabled, --no-auto-rerere skips the loop
        monkeypatch.setattr("builtins.input", lambda _: "y")

        with pytest.raises(SystemExit):
            cmd_propagate(_ns(no_auto_rerere=True))

        assert repo.git("rev-parse", "b") == b_original

    def test_auto_rerere_multi_commit_branch(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        repo.enable_rerere()
        repo.commit("f1.txt", "original1", "base1")
        repo.commit("f2.txt", "original2", "base2")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "f1.txt").write_text("b-version1")
        repo.git("add", "f1.txt", cwd=wt_b)
        repo.git("commit", "-m", "b modifies f1", cwd=wt_b)
        (wt_b / "f2.txt").write_text("b-version2")
        repo.git("add", "f2.txt", cwd=wt_b)
        repo.git("commit", "-m", "b modifies f2", cwd=wt_b)
        b_original = repo.git("rev-parse", "b")

        repo.checkout("main")
        repo.commit("f1.txt", "main-version1", "main modifies f1")
        repo.commit("f2.txt", "main-version2", "main modifies f2")

        # Record resolutions in b's worktree
        repo.git("rebase", "--onto", "main", b_original + "~2", cwd=wt_b, check=False)
        (wt_b / "f1.txt").write_text("resolved1")
        repo.git("add", "f1.txt", cwd=wt_b)
        repo.git("rebase", "--continue", cwd=wt_b, check=False)
        (wt_b / "f2.txt").write_text("resolved2")
        repo.git("add", "f2.txt", cwd=wt_b)
        repo.git("rebase", "--continue", cwd=wt_b)

        # Reset and propagate
        repo.git("reset", "--hard", b_original, cwd=wt_b)

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        out = capsys.readouterr().out
        assert "rerere" in out
        assert "resolved" in repo.git("show", "b:f1.txt")


class TestPropagateBranchArg:
    def test_propagate_from_named_branch(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        repo.commit("a1.txt", "a1", "advance main")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "on b", cwd=wt_b)
        repo.checkout("main")
        repo.commit("a2.txt", "a2", "new on main")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns(branch="main"))

        b_log = repo.git("log", "--oneline", "b")
        assert "new on main" in b_log

    def test_propagate_from_non_current_branch(
        self, repo: RepoHelper, monkeypatch, tmp_path
    ) -> None:
        repo.commit("a1.txt", "a1", "advance main")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "b1.txt").write_text("b1")
        repo.git("add", "b1.txt", cwd=wt_b)
        repo.git("commit", "-m", "on b", cwd=wt_b)
        repo.branch("c", parent="b")
        wt_c = repo.worktree("c", str(tmp_path / "wt-c"))
        (wt_c / "c1.txt").write_text("c1")
        repo.git("add", "c1.txt", cwd=wt_c)
        repo.git("commit", "-m", "on c", cwd=wt_c)

        repo.checkout("main")
        repo.commit("a2.txt", "a2", "new on main")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns(branch="main"))

        b_log = repo.git("log", "--oneline", "b")
        assert "new on main" in b_log
        c_log = repo.git("log", "--oneline", "c")
        assert "new on main" in c_log


class TestWorktreeValidation:
    def test_propagate_fails_without_worktree(self, repo: RepoHelper, monkeypatch, capsys) -> None:
        repo.branch("b", parent="main")
        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        with pytest.raises(SystemExit):
            cmd_propagate(_ns())

        err = capsys.readouterr().err
        assert "worktree" in err.lower()
        assert "b" in err

    def test_error_lists_all_missing(self, repo: RepoHelper, monkeypatch, capsys) -> None:
        repo.branch("b", parent="main")
        repo.branch("c", parent="main")
        repo.checkout("main")
        repo.commit("m2.txt", "m2", "advance")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        with pytest.raises(SystemExit):
            cmd_propagate(_ns())

        err = capsys.readouterr().err
        assert "b" in err
        assert "c" in err
