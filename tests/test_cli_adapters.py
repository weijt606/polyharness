"""Tests for CLI adapter system and CLIProposer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from poly_harness.proposer.adapters import (
    ADAPTER_REGISTRY,
    CLIAdapter,
    CLIResult,
    ClaudeCodeAdapter,
    ClawCodeAdapter,
    CodexAdapter,
    OpenCodeAdapter,
    get_adapter,
)
from poly_harness.proposer.cli_proposer import CLIProposer, _build_prompt


# ---------------------------------------------------------------------------
# Adapter registry & base
# ---------------------------------------------------------------------------

def test_registry_has_all_backends():
    assert set(ADAPTER_REGISTRY) == {"claude-code", "claw-code", "codex", "opencode"}


def test_get_adapter_valid():
    for backend in ADAPTER_REGISTRY:
        adapter = get_adapter(backend)
        assert isinstance(adapter, CLIAdapter)
        assert adapter.name == backend


def test_get_adapter_unknown():
    with pytest.raises(KeyError, match="Unknown CLI adapter"):
        get_adapter("does-not-exist")


# ---------------------------------------------------------------------------
# Individual adapters — build_command
# ---------------------------------------------------------------------------

def test_claude_code_command():
    adapter = ClaudeCodeAdapter()
    cmd = adapter.build_command("do stuff")
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "do stuff" in cmd


def test_claude_code_custom_path():
    adapter = ClaudeCodeAdapter()
    cmd = adapter.build_command("x", cli_path="/usr/bin/my-claude")
    assert cmd[0] == "/usr/bin/my-claude"


def test_claw_code_command():
    adapter = ClawCodeAdapter()
    cmd = adapter.build_command("improve harness")
    assert cmd[0] == "claw"
    assert "-p" in cmd
    assert "improve harness" in cmd


def test_codex_command():
    adapter = CodexAdapter()
    cmd = adapter.build_command("fix it")
    assert cmd[0] == "codex"
    assert "--quiet" in cmd
    assert "fix it" in cmd


def test_opencode_command():
    adapter = OpenCodeAdapter()
    cmd = adapter.build_command("optimize")
    assert cmd[0] == "opencode"
    assert "optimize" in cmd


# ---------------------------------------------------------------------------
# Adapter — parse_output
# ---------------------------------------------------------------------------

def test_parse_output_default():
    adapter = ClaudeCodeAdapter()
    result = adapter.parse_output("I changed harness.py", "", 0)
    assert isinstance(result, CLIResult)
    assert result.changes_summary == "I changed harness.py"
    assert result.returncode == 0


def test_parse_output_truncates_long():
    adapter = ClawCodeAdapter()
    long_text = "x" * 5000
    result = adapter.parse_output(long_text, "", 0)
    assert len(result.changes_summary) == 2000


def test_parse_output_empty():
    adapter = CodexAdapter()
    result = adapter.parse_output("", "", 0)
    assert result.changes_summary == ""


def test_env_vars_default_empty():
    for backend in ADAPTER_REGISTRY:
        adapter = get_adapter(backend)
        assert adapter.env_vars() == {}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def test_build_prompt_first_iteration(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cand = ws / "candidates" / "iter_0"
    cand.mkdir(parents=True)
    prompt = _build_prompt(ws, cand, 0, None)
    assert "Iteration: 0" in prompt
    assert "base_harness (first iteration)" in prompt
    assert "candidates/iter_0" in prompt


def test_build_prompt_with_parent(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cand = ws / "candidates" / "iter_3"
    cand.mkdir(parents=True)
    prompt = _build_prompt(ws, cand, 3, 1)
    assert "Iteration: 3" in prompt
    assert "iter_1" in prompt


def test_build_prompt_includes_leaderboard(tmp_path):
    ws = tmp_path / "ws"
    (ws / "summary").mkdir(parents=True)
    cand = ws / "candidates" / "iter_1"
    cand.mkdir(parents=True)
    lb = [{"iteration": 0, "overall_score": 0.8}]
    (ws / "summary" / "leaderboard.json").write_text(json.dumps(lb))

    prompt = _build_prompt(ws, cand, 1, 0)
    assert "Leaderboard" in prompt
    assert "0.8" in prompt


# ---------------------------------------------------------------------------
# CLIProposer
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "base_harness").mkdir(parents=True)
    (ws / "candidates" / "iter_0").mkdir(parents=True)
    (ws / "candidates" / "iter_0" / "harness.py").write_text("# base\n")
    return ws


def test_cli_proposer_success(tmp_path):
    """CLIProposer returns metadata when agent succeeds."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    # Mock subprocess.run to simulate a successful CLI agent
    mock_proc = type("Proc", (), {
        "stdout": "Improved the lexicon for better coverage.",
        "stderr": "",
        "returncode": 0,
    })()

    with patch("poly_harness.proposer.cli_proposer.subprocess.run", return_value=mock_proc):
        proposer = CLIProposer(backend="claude-code")
        result = proposer.propose(ws, cand, 0, None)

    assert "Improved the lexicon" in result["changes_summary"]
    assert result["proposer_model"] == "cli:claude-code"
    assert result["cli_returncode"] == 0


def test_cli_proposer_missing_binary(tmp_path):
    """Clear error when CLI binary is not installed."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    with patch(
        "poly_harness.proposer.cli_proposer.subprocess.run",
        side_effect=FileNotFoundError(),
    ):
        proposer = CLIProposer(backend="codex")
        with pytest.raises(RuntimeError, match="not found"):
            proposer.propose(ws, cand, 0, None)


def test_cli_proposer_timeout(tmp_path):
    """Clear error on timeout."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    import subprocess as sp

    with patch(
        "poly_harness.proposer.cli_proposer.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd="codex", timeout=600),
    ):
        proposer = CLIProposer(backend="codex", timeout=600)
        with pytest.raises(RuntimeError, match="timed out"):
            proposer.propose(ws, cand, 0, None)


def test_cli_proposer_nonzero_exit_with_output(tmp_path):
    """Non-zero exit but with output still returns result."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    mock_proc = type("Proc", (), {
        "stdout": "Partial changes applied.",
        "stderr": "warning: something",
        "returncode": 1,
    })()

    with patch("poly_harness.proposer.cli_proposer.subprocess.run", return_value=mock_proc):
        proposer = CLIProposer(backend="claw-code")
        result = proposer.propose(ws, cand, 0, None)

    assert result["changes_summary"] == "Partial changes applied."
    assert result["cli_returncode"] == 1


def test_cli_proposer_nonzero_exit_no_output(tmp_path):
    """Non-zero exit with no output raises RuntimeError."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    mock_proc = type("Proc", (), {
        "stdout": "",
        "stderr": "fatal error",
        "returncode": 1,
    })()

    with patch("poly_harness.proposer.cli_proposer.subprocess.run", return_value=mock_proc):
        proposer = CLIProposer(backend="opencode")
        with pytest.raises(RuntimeError, match="exited with code 1"):
            proposer.propose(ws, cand, 0, None)


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------

def test_factory_creates_cli_proposers():
    """create_proposer returns CLIProposer for all CLI backends."""
    from poly_harness.config import ProposerConfig
    from poly_harness.proposer import create_proposer

    for backend in ["claude-code", "claw-code", "codex", "opencode"]:
        config = ProposerConfig(backend=backend)
        proposer = create_proposer(config)
        assert isinstance(proposer, CLIProposer)
        assert proposer.backend == backend


def test_config_accepts_new_backends():
    """Config model accepts all 6 backend values."""
    from poly_harness.config import ProposerConfig

    for backend in ["api", "claude-code", "claw-code", "codex", "opencode", "local"]:
        cfg = ProposerConfig(backend=backend)
        assert cfg.backend == backend
