from __future__ import annotations

from git_tree.cli import cmd_propagate

from .conftest import RepoHelper


def _ns(*, dry: bool = False) -> object:
    import argparse

    return argparse.Namespace(dry=dry)


class TestPropagate:
    def test_linear_cascade(self, repo: RepoHelper, monkeypatch) -> None:
        repo.commit("a1.txt", "a1", "commit on main for b")
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("b1.txt", "b1", "commit on b")
        repo.branch("c", parent="b")
        repo.checkout("c")
        repo.commit("c1.txt", "c1", "commit on c")

        repo.checkout("main")
        repo.commit("a2.txt", "a2", "new commit on main")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        b_contains = repo.git("log", "--oneline", "b")
        assert "new commit on main" in b_contains

        c_contains = repo.git("log", "--oneline", "c")
        assert "new commit on main" in c_contains
        assert "commit on b" in c_contains

    def test_no_descendants_is_noop(self, repo: RepoHelper, monkeypatch, capsys) -> None:
        repo.branch("leaf", parent="main")
        repo.checkout("leaf")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())
        out = capsys.readouterr().out
        assert "No descendants" in out

    def test_conflict_skips_subtree(self, repo: RepoHelper, monkeypatch, capsys) -> None:
        repo.commit("shared.txt", "original", "base")
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("shared.txt", "from b", "b modifies shared")
        repo.branch("c", parent="b")
        repo.checkout("c")
        repo.commit("c1.txt", "c1", "commit on c")

        repo.checkout("main")
        repo.commit("shared.txt", "from main", "main modifies shared (conflict)")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())

        out = capsys.readouterr().out
        assert "CONFLICT" in out
        assert "skipped" in out.lower() or "ancestor failed" in out.lower()

    def test_already_up_to_date(self, repo: RepoHelper, monkeypatch, capsys) -> None:
        repo.branch("b", parent="main")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_propagate(_ns())
        out = capsys.readouterr().out
        assert "No descendants" not in out or "ok" in out.lower()

    def test_confirmation_decline_is_noop(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("b1.txt", "b1", "on b")
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

    def test_dry_does_not_modify(self, repo: RepoHelper, capsys) -> None:
        repo.commit("a1.txt", "a1", "base for b")
        repo.branch("b", parent="main")
        repo.checkout("b")
        repo.commit("b1.txt", "b1", "on b")
        repo.checkout("main")
        repo.commit("a2.txt", "a2", "advance main")

        b_tip_before = repo.git("rev-parse", "b")
        cmd_propagate(_ns(dry=True))

        assert repo.git("rev-parse", "b") == b_tip_before
        out = capsys.readouterr().out
        assert "Propagating from" in out
