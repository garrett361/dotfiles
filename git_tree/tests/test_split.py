from __future__ import annotations

import pytest

from git_tree.cli import TreeError, _root_remote, cmd_split, discover, roots

from .conftest import RepoHelper


class TestSplit:
    def test_splits_branch_into_parent_and_child(self, repo: RepoHelper, monkeypatch) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first on feature")
        repo.commit("f2.txt", "f2", "second on feature")
        repo.commit("f3.txt", "f3", "third on feature")

        commits = repo.git("log", "--oneline", "--reverse", "main..HEAD").splitlines()
        split_line = commits[1]

        inputs = iter(["feature-base", "n"])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(None)

        graph = discover()
        assert graph.parent_of["feature-base"] == "main"
        assert graph.parent_of["feature"] == "feature-base"

        split_hash = split_line.split()[0]
        base_tip_full = repo.git("rev-parse", "feature-base")
        assert base_tip_full.startswith(split_hash)

    def test_split_on_root_creates_new_root_parent(self, repo: RepoHelper, monkeypatch) -> None:
        # A root (no tree-parent) splits over its full history; the new parent becomes a
        # root and the original branch becomes its child.
        repo.git("branch", "base")  # root: no tree-parent
        repo.checkout("base")
        repo.commit("a1.txt", "a1", "first on base")
        repo.commit("a2.txt", "a2", "second on base")
        repo.commit("a3.txt", "a3", "third on base")

        commits = repo.git("log", "--oneline", "--reverse", "base").splitlines()
        split_line = commits[1]  # split after the second commit in full history

        inputs = iter(["base-bottom", "n"])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(None)

        graph = discover()
        # New parent is a root (no tree-parent); base is now its child.
        assert "base-bottom" not in graph.parent_of
        assert graph.parent_of["base"] == "base-bottom"
        assert roots(graph) == ["base-bottom"]
        # The split point is base-bottom's tip.
        split_hash = split_line.split()[0]
        assert repo.git("rev-parse", "base-bottom").startswith(split_hash)

    def test_split_root_carries_remote_to_new_root(self, repo: RepoHelper, monkeypatch) -> None:
        # The tree's remote lives on its root. Splitting a root inserts a new root above
        # it, so the anchor must follow or push can no longer resolve it.
        repo.git("branch", "base")
        repo.git("config", "branch.base.remote", "origin")
        repo.checkout("base")
        repo.commit("a1.txt", "a1", "first on base")
        repo.commit("a2.txt", "a2", "second on base")
        repo.commit("a3.txt", "a3", "third on base")

        split_line = repo.git("log", "--oneline", "--reverse", "base").splitlines()[1]
        inputs = iter(["base-bottom", "n"])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(None)

        # Resolution (what push uses) now anchors on the new root.
        assert _root_remote(discover(), "base") == ("base-bottom", "origin")
        assert repo.git("config", "branch.base-bottom.remote") == "origin"

    def test_split_child_does_not_create_remote(self, repo: RepoHelper, monkeypatch) -> None:
        # A child split keeps the same root, so nothing should migrate. The new mid-tree
        # parent must not acquire a remote key.
        repo.git("config", "branch.main.remote", "origin")
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first on feature")
        repo.commit("f2.txt", "f2", "second on feature")
        repo.commit("f3.txt", "f3", "third on feature")

        split_line = repo.git("log", "--oneline", "--reverse", "main..HEAD").splitlines()[1]
        inputs = iter(["feature-base", "n"])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(None)

        assert repo.git("config", "branch.feature-base.remote", check=False) == ""
        assert _root_remote(discover(), "feature") == ("main", "origin")

    def test_existing_parent_name_errors_cleanly(self, repo: RepoHelper, monkeypatch) -> None:
        # An already-taken parent name must surface a clean TreeError, not a raw
        # CalledProcessError traceback, and must fail before the worktree prompt
        # (only the name is read) without rewriting the child's tree-parent.
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first on feature")
        repo.commit("f2.txt", "f2", "second on feature")

        split_line = repo.git("log", "--oneline", "--reverse", "main..HEAD").splitlines()[0]
        inputs = iter(["main"])  # "main" already exists; no worktree prompt should follow
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        with pytest.raises(TreeError):
            cmd_split(None)

        assert discover().parent_of["feature"] == "main"

    def test_single_commit_exits(self, repo: RepoHelper) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "only commit")

        with pytest.raises(SystemExit):
            cmd_split(None)

    def test_creates_worktree_when_path_given(
        self, repo: RepoHelper, monkeypatch, tmp_path
    ) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first on feature")
        repo.commit("f2.txt", "f2", "second on feature")

        commits = repo.git("log", "--oneline", "--reverse", "main..HEAD").splitlines()
        split_line = commits[0]

        wt_path = str(tmp_path / "wt-parent")
        inputs = iter(["feature-parent", wt_path])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(None)

        worktrees = repo.git("worktree", "list", "--porcelain")
        assert "feature-parent" in worktrees
        assert (tmp_path / "wt-parent").exists()

    def test_worktree_failure_is_non_fatal(
        self, repo: RepoHelper, monkeypatch, capsys, tmp_path
    ) -> None:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first on feature")
        repo.commit("f2.txt", "f2", "second on feature")

        commits = repo.git("log", "--oneline", "--reverse", "main..HEAD").splitlines()
        split_line = commits[0]

        # A path that already exists as a file -> `git worktree add` fails.
        bad_path = tmp_path / "exists"
        bad_path.write_text("not a directory")

        inputs = iter(["feature-base", str(bad_path)])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(None)  # must not raise despite the worktree failure

        # The split itself was applied.
        graph = discover()
        assert graph.parent_of["feature-base"] == "main"
        assert graph.parent_of["feature"] == "feature-base"
        err = capsys.readouterr().err
        assert "could not create worktree" in err
