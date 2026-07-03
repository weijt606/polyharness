"""Tests for the shared WorkspaceToolkit (path containment, protected files, search)."""

from __future__ import annotations

from pathlib import Path

import pytest

from polyharness.proposer.toolkit import (
    PROTECTED_FILENAMES,
    WorkspaceToolkit,
    anthropic_tool_definitions,
    openai_tool_definitions,
)


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    cand = root / "candidates" / "iter_1"
    sibling = root / "candidates" / "iter_10"
    cand.mkdir(parents=True)
    sibling.mkdir(parents=True)
    (root / "search_log.jsonl").write_text('{"iteration": 0}\n')
    (cand / "harness.py").write_text("def solve():\n    return 'match_me'\n")
    (sibling / "score.json").write_text('{"overall_score": 0.9}')
    return root


@pytest.fixture()
def toolkit(ws: Path) -> WorkspaceToolkit:
    return WorkspaceToolkit(ws, ws / "candidates" / "iter_1")


class TestPathContainment:
    def test_write_inside_candidate_ok(self, toolkit: WorkspaceToolkit):
        result = toolkit.write("harness.py", "print('hi')")
        assert result.startswith("Wrote")

    def test_write_sibling_prefix_rejected(self, toolkit: WorkspaceToolkit, ws: Path):
        """Regression: startswith-based check let iter_1 write into iter_10."""
        result = toolkit.write("../iter_10/harness.py", "hacked")
        assert result.startswith("Error")
        assert not (ws / "candidates" / "iter_10" / "harness.py").exists()

    def test_write_workspace_escape_rejected(self, toolkit: WorkspaceToolkit, tmp_path: Path):
        result = toolkit.write("../../../evil.txt", "x")
        assert result.startswith("Error")
        assert not (tmp_path / "evil.txt").exists()

    def test_read_outside_workspace_rejected(self, toolkit: WorkspaceToolkit):
        assert toolkit.read("../../etc/passwd").startswith("Error")

    def test_read_sibling_prefix_dir_rejected(self, tmp_path: Path):
        """A sibling dir sharing the workspace name as prefix must not be readable."""
        root = tmp_path / "ws"
        (root / "candidates" / "iter_0").mkdir(parents=True)
        secret_dir = tmp_path / "ws_backup"
        secret_dir.mkdir()
        (secret_dir / "secret.txt").write_text("secret")
        tk = WorkspaceToolkit(root, root / "candidates" / "iter_0")
        assert tk.read("../ws_backup/secret.txt").startswith("Error")

    def test_list_dir_outside_rejected(self, toolkit: WorkspaceToolkit):
        assert toolkit.list_dir("..").startswith("Error")


class TestProtectedFiles:
    @pytest.mark.parametrize("name", sorted(PROTECTED_FILENAMES))
    def test_evaluator_artifacts_not_writable(self, toolkit: WorkspaceToolkit, name: str):
        result = toolkit.write(name, '{"overall_score": 1.0}')
        assert result.startswith("Error")

    def test_protected_names_in_subdir_also_blocked(self, toolkit: WorkspaceToolkit):
        assert toolkit.write("sub/score.json", "{}").startswith("Error")


class TestNoShellTool:
    def test_bash_is_not_a_tool(self, toolkit: WorkspaceToolkit):
        assert toolkit.execute("bash", {"command": "ls"}).startswith("Error: unknown tool")

    def test_no_bash_in_definitions(self):
        names = {t["name"] for t in anthropic_tool_definitions()}
        assert "bash" not in names
        oai_names = {t["function"]["name"] for t in openai_tool_definitions()}
        assert "bash" not in oai_names
        assert names == oai_names  # both protocols expose the same tools


class TestTools:
    def test_read_write_roundtrip(self, toolkit: WorkspaceToolkit):
        toolkit.write("new.py", "x = 1\n")
        assert toolkit.read("candidates/iter_1/new.py") == "x = 1\n"

    def test_read_other_candidates_allowed(self, toolkit: WorkspaceToolkit):
        content = toolkit.read("candidates/iter_10/score.json")
        assert "overall_score" in content

    def test_search_finds_matches(self, toolkit: WorkspaceToolkit):
        result = toolkit.search("match_me")
        assert "harness.py:2" in result

    def test_search_invalid_regex(self, toolkit: WorkspaceToolkit):
        assert toolkit.search("[unclosed").startswith("Error: invalid regex")

    def test_search_outside_rejected(self, toolkit: WorkspaceToolkit):
        assert toolkit.search("x", "../..").startswith("Error")

    def test_execute_dispatch(self, toolkit: WorkspaceToolkit):
        assert "search_log.jsonl" in toolkit.execute("list_dir", {"path": "."})
        assert toolkit.execute("nope", {}).startswith("Error: unknown tool")

    def test_execute_never_raises(self, toolkit: WorkspaceToolkit):
        # Missing args must come back as an error string, not an exception.
        assert isinstance(toolkit.execute("file_read", {}), str)
        assert isinstance(toolkit.execute("file_write", {}), str)
