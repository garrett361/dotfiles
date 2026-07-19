from __future__ import annotations

import json

import pytest

from git_tree.cli import SCHEMA_VERSION, main

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
        assert obj["ok"] is False and obj["error"]["code"] == 4
