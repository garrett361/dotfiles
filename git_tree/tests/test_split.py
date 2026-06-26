from __future__ import annotations

import argparse

import pytest

from git_tree.cli import TreeError, _root_remote, cmd_split, discover, roots

from .conftest import RepoHelper


def _ns(**kwargs) -> object:
    # cmd_split reads each field via getattr; supply the four split fields explicitly.
    fields = {"after": None, "name": None, "worktree": None, "no_worktree": False}
    fields.update(kwargs)
    return argparse.Namespace(command="split", **fields)


def _no_prompt(*_args, **_kwargs):
    raise AssertionError("interactive prompt should not be reached")


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


class TestSplitNonInteractive:
    def _feature_with_three_commits(self, repo: RepoHelper) -> list[str]:
        repo.branch("feature", parent="main")
        repo.checkout("feature")
        repo.commit("f1.txt", "f1", "first on feature")
        repo.commit("f2.txt", "f2", "second on feature")
        repo.commit("f3.txt", "f3", "third on feature")
        return repo.git("log", "--oneline", "--reverse", "main..HEAD").splitlines()

    def test_child_split_no_worktree(self, repo: RepoHelper, monkeypatch) -> None:
        split_hash = self._feature_with_three_commits(repo)[1].split()[0]
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", _no_prompt)

        cmd_split(_ns(after=split_hash, name="feature-base", no_worktree=True))

        graph = discover()
        assert graph.parent_of["feature-base"] == "main"
        assert graph.parent_of["feature"] == "feature-base"
        assert repo.git("rev-parse", "feature-base").startswith(split_hash)
        # No worktree for the new parent.
        assert "branch refs/heads/feature-base" not in repo.git("worktree", "list", "--porcelain")

    def test_worktree_flag_creates_worktree(self, repo: RepoHelper, monkeypatch, tmp_path) -> None:
        split_hash = self._feature_with_three_commits(repo)[1].split()[0]
        # A literal path the tri-state must treat as a path, not the "n" skip sentinel.
        wt = str(tmp_path / "wt-parent")
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", _no_prompt)

        cmd_split(_ns(after=split_hash, name="feature-base", worktree=wt))

        assert "branch refs/heads/feature-base" in repo.git("worktree", "list", "--porcelain")
        assert (tmp_path / "wt-parent").exists()

    def test_after_out_of_range_raises_nothing_created(self, repo: RepoHelper, monkeypatch) -> None:
        self._feature_with_three_commits(repo)
        # `main` is feature's fork point (not unique to feature) -> outside old_fork..HEAD.
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", _no_prompt)

        with pytest.raises(TreeError):
            cmd_split(_ns(after="main", name="feature-base", no_worktree=True))

        assert repo.git("rev-parse", "--verify", "refs/heads/feature-base", check=False) == ""
        assert discover().parent_of["feature"] == "main"  # child untouched

    def test_after_invalid_commit_raises(self, repo: RepoHelper, monkeypatch) -> None:
        self._feature_with_three_commits(repo)
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", _no_prompt)
        with pytest.raises(TreeError):
            cmd_split(_ns(after="no-such-ref", name="feature-base", no_worktree=True))
        assert repo.git("rev-parse", "--verify", "refs/heads/feature-base", check=False) == ""

    def test_omitted_flags_still_interactive(self, repo: RepoHelper, monkeypatch) -> None:
        # A Namespace with all split fields None/False must fall back to the prompts,
        # exactly like the bare cmd_split(None) path.
        split_line = self._feature_with_three_commits(repo)[1]
        inputs = iter(["feature-base", "n"])
        monkeypatch.setattr("git_tree.cli.fzf_select", lambda items, **kw: [split_line])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        cmd_split(_ns())

        graph = discover()
        assert graph.parent_of["feature-base"] == "main"
        assert graph.parent_of["feature"] == "feature-base"

    def test_worktree_flag_literal_n_is_a_path(self, repo, monkeypatch, tmp_path) -> None:
        # In flag mode a literal path named "n" is a path, not the interactive skip sentinel.
        split_hash = self._feature_with_three_commits(repo)[1].split()[0]
        wt = str(tmp_path / "n")
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", _no_prompt)

        cmd_split(_ns(after=split_hash, name="feature-base", worktree=wt))

        assert "branch refs/heads/feature-base" in repo.git("worktree", "list", "--porcelain")
        assert (tmp_path / "n").exists()

    def test_after_given_name_prompted(self, repo, monkeypatch) -> None:
        # Partial mode: --after supplied (fzf must NOT run), name comes from the prompt.
        split_hash = self._feature_with_three_commits(repo)[1].split()[0]
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", lambda _: "feature-base")

        cmd_split(_ns(after=split_hash, no_worktree=True))

        graph = discover()
        assert graph.parent_of["feature-base"] == "main"
        assert graph.parent_of["feature"] == "feature-base"

    def test_root_split_via_after_carries_remote(self, repo, monkeypatch) -> None:
        # Root split through --after: old_fork is None (only the ancestor-of-HEAD check
        # applies) and the tree remote must migrate to the new root.
        repo.git("branch", "base")
        repo.git("config", "branch.base.remote", "origin")
        repo.checkout("base")
        repo.commit("a1.txt", "a1", "first on base")
        repo.commit("a2.txt", "a2", "second on base")
        repo.commit("a3.txt", "a3", "third on base")
        split_hash = repo.git("log", "--oneline", "--reverse", "base").splitlines()[1].split()[0]
        monkeypatch.setattr("git_tree.cli.fzf_select", _no_prompt)
        monkeypatch.setattr("builtins.input", _no_prompt)

        cmd_split(_ns(after=split_hash, name="base-bottom", no_worktree=True))

        graph = discover()
        assert "base-bottom" not in graph.parent_of  # new root
        assert graph.parent_of["base"] == "base-bottom"
        assert _root_remote(graph, "base") == ("base-bottom", "origin")
