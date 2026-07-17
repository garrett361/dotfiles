from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import pytest

from git_tree.cli import TreeError, cmd_branch, cmd_propagate, cmd_repair, discover

from .conftest import RepoHelper, _git


def _add_submodule(repo: RepoHelper, name: str, tmp_path: Path) -> Path:
    """Create a sub-repo and add it as a submodule. Returns submodule path in worktree."""
    sub_repo = tmp_path / f"sub-{name}"
    sub_repo.mkdir()
    _git("init", cwd=sub_repo)
    _git("config", "user.email", "test@test.com", cwd=sub_repo)
    _git("config", "user.name", "Test", cwd=sub_repo)
    (sub_repo / "readme.txt").write_text("sub content")
    _git("add", "readme.txt", cwd=sub_repo)
    _git("commit", "-m", "sub init", cwd=sub_repo)
    # Allow file:// transport for submodule clone
    repo.git("-c", "protocol.file.allow=always", "submodule", "add", str(sub_repo), name)
    repo.git("commit", "-m", f"add submodule {name}")
    return repo.work / name


def _corrupt_submodule(worktree: Path, submodule_path: str) -> None:
    """Corrupt a submodule's .git pointer so health check fails."""
    dot_git = worktree / submodule_path / ".git"
    dot_git.write_text("gitdir: /nonexistent/path/that/does/not/exist\n")


class TestRepair:
    def _ns(self, branch: str | None = None, yes: bool = True, force: bool = False):
        return argparse.Namespace(branch=branch, yes=yes, force=force)

    def test_repair_recreates_worktree(self, repo: RepoHelper, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")

        _add_submodule(repo, "mysub", tmp_path)
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))
        _git("submodule", "update", "--init", "--recursive", cwd=wt)

        _corrupt_submodule(wt, "mysub")

        cmd_repair(self._ns("child"))
        assert wt.exists()
        assert (wt / "mysub" / ".git").exists()

    def test_repair_handles_corrupted_worktree_contents(
        self, repo: RepoHelper, tmp_path
    ) -> None:
        """Worktree directory exists but internals are broken (e.g. .git file deleted)."""
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))

        # Corrupt the worktree by removing its .git file (makes git status fail)
        (wt / ".git").unlink()
        (wt / ".git").write_text("garbage\n")

        cmd_repair(self._ns("child", force=True))
        assert wt.exists()
        assert (wt / "init.txt").exists()

    def test_repair_rejects_non_tree_branch(self, repo: RepoHelper, capsys) -> None:
        with pytest.raises(TreeError):
            cmd_repair(self._ns("main"))
        assert "not a repairable tree-branch" in capsys.readouterr().err

    def test_repair_rejects_no_worktree(self, repo: RepoHelper, capsys) -> None:
        repo.branch("orphan", parent="main")
        with pytest.raises(TreeError):
            cmd_repair(self._ns("orphan"))
        assert "has no worktree" in capsys.readouterr().err

    def test_repair_refuses_dirty_without_force(
        self, repo: RepoHelper, tmp_path, capsys
    ) -> None:
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))
        repo.dirty(cwd=wt)

        with pytest.raises(TreeError):
            cmd_repair(self._ns("child", force=False))
        assert "uncommitted changes" in capsys.readouterr().err

    def test_repair_allows_dirty_with_force(self, repo: RepoHelper, tmp_path) -> None:
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))
        repo.dirty(cwd=wt)

        cmd_repair(self._ns("child", force=True))
        assert wt.exists()
        assert not (wt / "dirty.txt").exists()

    def test_repair_preserves_tree_config(self, repo: RepoHelper, tmp_path) -> None:
        repo.branch("child", parent="main")
        repo.worktree("child", str(tmp_path / "wt-child"))

        cmd_repair(self._ns("child"))
        graph = discover()
        assert graph.parent_of["child"] == "main"


class TestBranchSubmoduleInit:
    def test_branch_inits_submodules(
        self, repo: RepoHelper, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")

        _add_submodule(repo, "mysub", tmp_path)

        wt_path = str(tmp_path / "wt-child")
        cmd_branch(argparse.Namespace(command="branch", name="child", path=wt_path))

        assert (Path(wt_path) / "mysub" / ".git").exists()
        assert (Path(wt_path) / "mysub" / "readme.txt").exists()

    def test_branch_no_submodule_init_flag(
        self, repo: RepoHelper, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")

        _add_submodule(repo, "mysub", tmp_path)

        wt_path = str(tmp_path / "wt-child")
        cmd_branch(
            argparse.Namespace(
                command="branch", name="child", path=wt_path, no_submodule_init=True
            )
        )

        assert (Path(wt_path) / "mysub").exists()
        assert not (Path(wt_path) / "mysub" / "readme.txt").exists()


class TestPropagateSubmoduleHealth:
    def test_propagate_detects_unhealthy_submodule(
        self, repo: RepoHelper, tmp_path, capsys, monkeypatch
    ) -> None:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")

        _add_submodule(repo, "mysub", tmp_path)
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))
        _git("submodule", "update", "--init", "--recursive", cwd=wt)

        repo.checkout("main")
        repo.commit("extra.txt", "extra", "advance main")

        _corrupt_submodule(wt, "mysub")

        with pytest.raises(TreeError):
            cmd_propagate(
                argparse.Namespace(
                    dry_run=False, no_auto_rerere=False, branch=None, yes=True
                )
            )
        err = capsys.readouterr().err
        assert "corrupted submodule state" in err

    def test_propagate_passes_with_uninitialized_submodules(
        self, repo: RepoHelper, tmp_path, monkeypatch
    ) -> None:
        """Uninitialized submodules (no .git) should NOT block propagate."""
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")

        _add_submodule(repo, "mysub", tmp_path)
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))

        repo.checkout("main")
        repo.commit("extra.txt", "extra", "advance main")

        cmd_propagate(
            argparse.Namespace(
                dry_run=False, no_auto_rerere=False, branch=None, yes=True
            )
        )
        log = _git("log", "--oneline", "child", cwd=repo.work)
        assert "advance main" in log

    def test_propagate_suggests_repair(
        self, repo: RepoHelper, tmp_path, capsys, monkeypatch
    ) -> None:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")

        _add_submodule(repo, "mysub", tmp_path)
        repo.branch("child", parent="main")
        wt = repo.worktree("child", str(tmp_path / "wt-child"))
        _git("submodule", "update", "--init", "--recursive", cwd=wt)

        repo.checkout("main")
        repo.commit("extra.txt", "extra", "advance main")

        _corrupt_submodule(wt, "mysub")

        with pytest.raises(TreeError):
            cmd_propagate(
                argparse.Namespace(
                    dry_run=False, no_auto_rerere=False, branch=None, yes=True
                )
            )
        err = capsys.readouterr().err
        assert "git tree repair" in err
