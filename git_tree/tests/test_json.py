from __future__ import annotations

import json

import pytest

from git_tree.cli import SCHEMA_VERSION, _has_active_rebase, main

from .conftest import RepoHelper


class TestSuccessEnvelope:
    def test_minimal_success(self, repo: RepoHelper, capsys) -> None:
        # No-op propagate on a rootless main: a bare success envelope, no `data`.
        main(["propagate", "--json", "-y"])
        obj = json.loads(capsys.readouterr().out)
        assert obj["schema_version"] == SCHEMA_VERSION
        assert obj["tool_version"]
        assert obj["command"] == "propagate"
        assert obj["ok"] is True
        assert "error" not in obj

    def test_forest_envelope_is_backward_compatible(self, repo: RepoHelper, capsys) -> None:
        repo.branch("feat", parent="main")
        main(["--json"])
        obj = json.loads(capsys.readouterr().out)
        assert obj["command"] == "tree" and obj["ok"] is True
        # The existing forest keys remain present as envelope siblings.
        assert obj["roots"] == ["main"]
        assert {b["name"] for b in obj["branches"]} >= {"main", "feat"}

    def test_stdout_is_exactly_one_json_object(self, repo: RepoHelper, capsys, tmp_path) -> None:
        repo.branch("feat", parent="main")
        repo.worktree("feat", str(tmp_path / "wt-feat"))
        repo.commit("m2.txt", "m2", "advance")
        main(["propagate", "--json", "-y"])
        out = capsys.readouterr().out
        json.loads(out)  # parses as a single object
        assert "+ git" not in out  # git_echo diagnostics went to stderr, not stdout


class TestErrorEnvelope:
    def test_not_a_tree_branch(self, repo: RepoHelper, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["push", "--json"])
        assert exc.value.code == 5
        err = json.loads(capsys.readouterr().out)["error"]
        assert err["kind"] == "not_a_tree_branch"
        assert err["code"] == 5
        assert err["message"]

    def test_log_json_is_usage_error(self, repo: RepoHelper, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["log", "--json"])
        assert exc.value.code == 2
        assert json.loads(capsys.readouterr().out)["error"]["kind"] == "usage"

    def test_json_implies_non_interactive(self, repo: RepoHelper, capsys) -> None:
        # `attach` with no parent would prompt; --json alone must error, no --no-input needed.
        repo.git("branch", "solo")
        repo.checkout("solo")
        with pytest.raises(SystemExit) as exc:
            main(["attach", "--json"])
        assert exc.value.code == 4
        obj = json.loads(capsys.readouterr().out)
        assert obj["ok"] is False and obj["error"]["kind"] == "input_required"

    def test_confirmation_required(self, repo: RepoHelper, capsys, tmp_path) -> None:
        repo.branch("feat", parent="main")
        repo.worktree("feat", str(tmp_path / "wt-feat"))
        with pytest.raises(SystemExit) as exc:
            main(["remove", "feat", "--json"])
        assert exc.value.code == 4
        err = json.loads(capsys.readouterr().out)["error"]
        assert err["kind"] == "confirmation_required"
        assert "remedy" not in err  # the agent already knows its own command
        assert "-y" in err["message"]  # the message names the flag to add

    def test_conflict_envelope(self, repo: RepoHelper, capsys, tmp_path) -> None:
        repo.commit("shared.txt", "base", "base")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "shared.txt").write_text("from b")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("commit", "-m", "b change", cwd=wt_b)
        repo.checkout("main")
        repo.commit("shared.txt", "from main", "conflicting change")
        with pytest.raises(SystemExit) as exc:
            main(["propagate", "main", "--json", "-y"])
        assert exc.value.code == 3
        err = json.loads(capsys.readouterr().out)["error"]
        assert err["kind"] == "conflict"
        assert err["branch"] == "b"
        assert err["conflicted_files"] == ["shared.txt"]
        assert err["worktree"]
        assert err["remedy"] == ["git", "tree", "continue"]


class TestContinue:
    def _stop_on_conflict(self, repo: RepoHelper, capsys, tmp_path):
        repo.commit("shared.txt", "base", "base")
        repo.branch("b", parent="main")
        wt_b = repo.worktree("b", str(tmp_path / "wt-b"))
        (wt_b / "shared.txt").write_text("from b")
        repo.git("add", "shared.txt", cwd=wt_b)
        repo.git("commit", "-m", "b change", cwd=wt_b)
        repo.checkout("main")
        repo.commit("shared.txt", "from main", "conflicting change")
        with pytest.raises(SystemExit) as exc:
            main(["propagate", "main", "--no-input", "-y"])
        assert exc.value.code == 3
        capsys.readouterr()  # drain setup output so the next envelope stands alone
        return wt_b

    def test_resumes_after_resolution(self, repo: RepoHelper, capsys, tmp_path) -> None:
        wt_b = self._stop_on_conflict(repo, capsys, tmp_path)
        (wt_b / "shared.txt").write_text("resolved")
        repo.git("add", "shared.txt", cwd=wt_b)
        main(["continue", "--json"])
        obj = json.loads(capsys.readouterr().out)
        assert obj["command"] == "continue" and obj["ok"] is True
        assert "b change" in repo.git("log", "--oneline", "b")  # b is rebased onto main
        assert not _has_active_rebase(wt_b)  # rebase finished

    def test_unresolved_conflicts_errors(self, repo: RepoHelper, capsys, tmp_path) -> None:
        self._stop_on_conflict(repo, capsys, tmp_path)  # leave it unresolved
        with pytest.raises(SystemExit) as exc:
            main(["continue", "--json"])
        assert exc.value.code == 4
        assert json.loads(capsys.readouterr().out)["error"]["kind"] == "unresolved_conflicts"

    def test_no_rebase_in_progress_errors(self, repo: RepoHelper, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["continue", "--json"])
        assert exc.value.code == 4
        assert json.loads(capsys.readouterr().out)["ok"] is False
