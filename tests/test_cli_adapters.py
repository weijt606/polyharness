"""Tests for CLI adapter system and CLIProposer."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from polyharness.proposer.adapters import (
    ADAPTER_REGISTRY,
    ClaudeCodeAdapter,
    ClawCodeAdapter,
    CLIAdapter,
    CLIResult,
    CodexAdapter,
    HermesAdapter,
    OpenCodeAdapter,
    PiAdapter,
    get_adapter,
)
from polyharness.proposer.cli_proposer import CLIProposer, _build_prompt

# ---------------------------------------------------------------------------
# Adapter registry & base
# ---------------------------------------------------------------------------

def test_registry_has_all_backends():
    assert set(ADAPTER_REGISTRY) == {
        "claude-code", "claw-code", "codex", "hermes", "opencode", "pi"
    }


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
    # Pinned to Opus 4.7
    assert "--model" in cmd
    from polyharness.config import DEFAULT_CLAUDE_CODE_MODEL

    assert DEFAULT_CLAUDE_CODE_MODEL in cmd
    assert DEFAULT_CLAUDE_CODE_MODEL == "claude-opus-4-8"
    # Headless edits must be auto-approved or the agent can't write candidates
    assert "--permission-mode" in cmd
    assert "acceptEdits" in cmd
    # --verbose is noise in print mode; should be gone
    assert "--verbose" not in cmd


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
    # --verbose floods the stdout tail that parse_output keeps as the
    # change summary (same reasoning as claude-code).
    assert "--verbose" not in cmd


def test_codex_command():
    adapter = CodexAdapter()
    cmd = adapter.build_command("fix it")
    assert cmd[0] == "codex"
    assert "exec" in cmd                    # headless mode (replaces old --quiet)
    assert "--skip-git-repo-check" in cmd   # workspace isn't a git repo
    assert "--quiet" not in cmd             # removed upstream
    assert "fix it" in cmd


def test_opencode_command():
    adapter = OpenCodeAdapter()
    cmd = adapter.build_command("optimize")
    assert cmd[0] == "opencode"
    assert "run" in cmd          # non-interactive subcommand (replaces old -p)
    assert "-p" not in cmd       # no longer supported upstream
    assert "optimize" in cmd


def test_hermes_command():
    adapter = HermesAdapter()
    cmd = adapter.build_command("improve harness")
    assert cmd[0] == "hermes"
    assert "chat" in cmd
    assert "-q" in cmd
    assert "improve harness" in cmd


def test_pi_command():
    adapter = PiAdapter()
    cmd = adapter.build_command("evolve it")
    assert cmd[0] == "pi"
    assert "-p" in cmd          # print mode: single-shot, non-interactive
    assert "evolve it" in cmd
    # pi has no permission/sandbox flags by design — none should be added
    assert "--permission-mode" not in cmd
    assert "--sandbox" not in cmd


def test_pi_custom_path():
    adapter = PiAdapter()
    cmd = adapter.build_command("x", cli_path="/opt/bin/pi")
    assert cmd[0] == "/opt/bin/pi"


def test_hermes_custom_path():
    adapter = HermesAdapter()
    cmd = adapter.build_command("x", cli_path="/usr/local/bin/hermes")
    assert cmd[0] == "/usr/local/bin/hermes"


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


def test_proposer_prompts_include_improvement_principles(tmp_path):
    """Both the CLI and API proposer prompts carry the shared improvement principles."""
    from polyharness.proposer.api_proposer import _build_system_prompt
    from polyharness.proposer.base import PROPOSER_PRINCIPLES

    ws = tmp_path / "ws"
    cand = ws / "candidates" / "iter_1"
    cand.mkdir(parents=True)

    cli_prompt = _build_prompt(ws, cand, 1, 0)
    api_prompt = _build_system_prompt(ws, cand, 1, 0)

    # The anti-parameter-tuning directive is the distinctive marker.
    assert "parameter variant" in PROPOSER_PRINCIPLES
    assert "parameter variant" in cli_prompt
    assert "parameter variant" in api_prompt
    assert "falsifiable hypothesis" in cli_prompt


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

    # Mock the process-group runner to simulate a successful CLI agent
    from polyharness.utils.proc import ProcResult

    mock_proc = ProcResult(
        returncode=0,
        stdout="Improved the lexicon for better coverage.",
        stderr="",
    )

    with patch("polyharness.proposer.cli_proposer.run_process_group", return_value=mock_proc):
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
        "polyharness.proposer.cli_proposer.run_process_group",
        side_effect=FileNotFoundError(),
    ):
        proposer = CLIProposer(backend="codex")
        with pytest.raises(RuntimeError, match="not found"):
            proposer.propose(ws, cand, 0, None)


def test_cli_proposer_not_executable(tmp_path):
    """Clear error when CLI binary exists but lacks execute permission."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    with patch(
        "polyharness.proposer.cli_proposer.run_process_group",
        side_effect=PermissionError(),
    ):
        proposer = CLIProposer(backend="codex")
        with pytest.raises(RuntimeError, match="not executable"):
            proposer.propose(ws, cand, 0, None)


def test_cli_proposer_timeout(tmp_path):
    """Clear error on timeout, with partial output preserved."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    from polyharness.utils.proc import ProcResult

    mock_proc = ProcResult(returncode=-1, stdout="partial work...", stderr="", timed_out=True)

    with patch(
        "polyharness.proposer.cli_proposer.run_process_group",
        return_value=mock_proc,
    ):
        proposer = CLIProposer(backend="codex", timeout=600)
        with pytest.raises(RuntimeError, match="timed out"):
            proposer.propose(ws, cand, 0, None)


def test_cli_proposer_nonzero_exit_with_output(tmp_path):
    """Non-zero exit but with output still returns result."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    from polyharness.utils.proc import ProcResult

    mock_proc = ProcResult(
        returncode=1,
        stdout="Partial changes applied.",
        stderr="warning: something",
    )

    with patch("polyharness.proposer.cli_proposer.run_process_group", return_value=mock_proc):
        proposer = CLIProposer(backend="claw-code")
        result = proposer.propose(ws, cand, 0, None)

    assert result["changes_summary"] == "Partial changes applied."
    assert result["cli_returncode"] == 1


def test_cli_proposer_nonzero_exit_no_output(tmp_path):
    """Non-zero exit with no output raises RuntimeError."""
    ws = _make_workspace(tmp_path)
    cand = ws / "candidates" / "iter_0"

    from polyharness.utils.proc import ProcResult

    mock_proc = ProcResult(returncode=1, stdout="", stderr="fatal error")

    with patch("polyharness.proposer.cli_proposer.run_process_group", return_value=mock_proc):
        proposer = CLIProposer(backend="opencode")
        with pytest.raises(RuntimeError, match="exited with code 1"):
            proposer.propose(ws, cand, 0, None)


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------

def test_factory_creates_cli_proposers():
    """create_proposer returns CLIProposer for all CLI backends."""
    from polyharness.config import ProposerConfig
    from polyharness.proposer import create_proposer

    for backend in ["claude-code", "claw-code", "codex", "hermes", "opencode", "pi"]:
        config = ProposerConfig(backend=backend)  # type: ignore[arg-type]
        proposer = create_proposer(config)
        assert isinstance(proposer, CLIProposer)
        assert proposer.backend == backend


def test_config_accepts_new_backends():
    """Config model accepts all CLI + non-CLI backend values."""
    from polyharness.config import ProposerConfig

    for backend in ["api", "claude-code", "claw-code", "codex", "opencode", "pi", "local"]:
        cfg = ProposerConfig(backend=backend)  # type: ignore[arg-type]
        assert cfg.backend == backend
