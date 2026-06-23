"""Ref resolution edge cases (Unit 2): detached HEAD and main_branch fallback."""

from __future__ import annotations

import pytest

from git_tree.cli import TreeError, current_branch, main_branch

from .conftest import RepoHelper


class TestCurrentBranch:
    def test_rejects_detached_head(self, repo: RepoHelper) -> None:
        repo.git("checkout", "--detach")
        with pytest.raises(TreeError):
            current_branch()

    def test_returns_branch_name_when_attached(self, repo: RepoHelper) -> None:
        assert current_branch() == "main"


class TestMainBranch:
    def test_prefers_main(self, repo: RepoHelper) -> None:
        assert main_branch() == "main"

    def test_detects_non_standard_remote_default(self, repo: RepoHelper) -> None:
        # Repo whose trunk is `trunk`, not main/master.
        repo.git("branch", "-m", "main", "trunk")
        repo.git("push", "origin", "trunk")
        repo.git("remote", "set-head", "origin", "trunk")
        # Must detect `trunk`, not misreport the literal "main".
        assert main_branch() == "trunk"

    def test_ignores_remote_default_absent_locally(self, repo: RepoHelper) -> None:
        # origin/HEAD -> origin/trunk, but no local trunk and no local main/master.
        repo.git("push", "origin", "main:trunk")
        repo.git("remote", "set-head", "origin", "trunk")
        repo.git("branch", "-m", "main", "dev")
        assert main_branch() == "main"  # guard rejects a remote default absent locally

    def test_falls_back_when_no_origin_default(self, repo: RepoHelper) -> None:
        repo.git("branch", "-m", "main", "trunk")
        repo.git("remote", "remove", "origin")
        assert main_branch() == "main"
