"""Tests for online evolution CLI commands (v0.2.0): wrap, traces, evolve."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from polyharness.cli import main


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def store_dir(tmp_path: Path) -> Path:
    d = tmp_path / "traces"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# ph wrap
# ---------------------------------------------------------------------------


class TestWrap:
    def test_wrap_help(self, runner: CliRunner):
        result = runner.invoke(main, ["wrap", "--help"])
        assert result.exit_code == 0
        assert "Wrap an Agent CLI" in result.output

    def test_wrap_runs_command(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(
            main, ["wrap", "--store", str(store_dir), "echo", "hello"]
        )
        assert "hello" in result.output
        # Trace should be recorded
        traces = list(store_dir.iterdir())
        assert len(traces) == 1
        meta = json.loads((traces[0] / "meta.json").read_text())
        assert meta["agent"] == "echo"
        assert meta["exit_code"] == 0

    def test_wrap_records_output(self, runner: CliRunner, store_dir: Path):
        runner.invoke(
            main, ["wrap", "--store", str(store_dir), "echo", "captured"]
        )
        traces = list(store_dir.iterdir())
        stdout_file = traces[0] / "stdout.txt"
        assert stdout_file.exists()
        assert "captured" in stdout_file.read_text()

    def test_wrap_no_record_output(self, runner: CliRunner, store_dir: Path):
        runner.invoke(
            main,
            ["wrap", "--store", str(store_dir), "--no-record-output", "echo", "secret"],
        )
        traces = list(store_dir.iterdir())
        assert not (traces[0] / "stdout.txt").exists()

    def test_wrap_command_not_found(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(
            main, ["wrap", "--store", str(store_dir), "nonexistent_cmd_xyz"]
        )
        assert result.exit_code == 127


# ---------------------------------------------------------------------------
# ph traces
# ---------------------------------------------------------------------------


class TestTraces:
    def test_traces_list_empty(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(main, ["traces", "list", "--store", str(store_dir)])
        assert result.exit_code == 0
        assert "No traces" in result.output

    def test_traces_list_with_data(self, runner: CliRunner, store_dir: Path):
        # Record a trace via wrap first
        runner.invoke(main, ["wrap", "--store", str(store_dir), "echo", "test"])
        result = runner.invoke(main, ["traces", "list", "--store", str(store_dir)])
        assert result.exit_code == 0
        assert "echo" in result.output

    def test_traces_show(self, runner: CliRunner, store_dir: Path):
        runner.invoke(main, ["wrap", "--store", str(store_dir), "echo", "detail"])
        traces = list(store_dir.iterdir())
        trace_id = traces[0].name

        result = runner.invoke(
            main, ["traces", "show", trace_id, "--store", str(store_dir)]
        )
        assert result.exit_code == 0
        assert "echo" in result.output

    def test_traces_show_not_found(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(
            main, ["traces", "show", "nonexistent", "--store", str(store_dir)]
        )
        assert result.exit_code != 0

    def test_traces_stats_empty(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(main, ["traces", "stats", "--store", str(store_dir)])
        assert result.exit_code == 0
        assert "Total traces" in result.output
        assert "0" in result.output

    def test_traces_stats_with_data(self, runner: CliRunner, store_dir: Path):
        for _ in range(3):
            runner.invoke(main, ["wrap", "--store", str(store_dir), "echo", "x"])
        result = runner.invoke(main, ["traces", "stats", "--store", str(store_dir)])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_traces_clear(self, runner: CliRunner, store_dir: Path):
        for _ in range(3):
            runner.invoke(main, ["wrap", "--store", str(store_dir), "echo", "x"])
        result = runner.invoke(
            main, ["traces", "clear", "-y", "--store", str(store_dir)]
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        # Verify cleared
        result2 = runner.invoke(main, ["traces", "stats", "--store", str(store_dir)])
        assert "0" in result2.output

    def test_traces_clear_keep(self, runner: CliRunner, store_dir: Path):
        import time

        for _ in range(5):
            runner.invoke(main, ["wrap", "--store", str(store_dir), "echo", "x"])
            time.sleep(0.01)
        result = runner.invoke(
            main, ["traces", "clear", "-y", "--keep", "2", "--store", str(store_dir)]
        )
        assert result.exit_code == 0
        assert "Removed 3" in result.output


# ---------------------------------------------------------------------------
# ph evolve
# ---------------------------------------------------------------------------


class TestEvolve:
    def test_evolve_help(self, runner: CliRunner):
        result = runner.invoke(main, ["evolve", "--help"])
        assert result.exit_code == 0
        assert "evolution" in result.output.lower()

    def test_evolve_no_workspace(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            main, ["evolve", "--workspace", str(tmp_path / "nope")]
        )
        assert result.exit_code != 0

    def test_evolve_no_traces(self, runner: CliRunner, tmp_path: Path, store_dir: Path):
        """Evolve should fail gracefully when no traces collected."""
        from polyharness.workspace import Workspace

        ws = Workspace.init(tmp_path / "ws", agent_backend="local")

        result = runner.invoke(
            main,
            ["evolve", "--workspace", str(ws.root), "--store", str(store_dir)],
        )
        assert result.exit_code != 0
        assert "No traces" in result.output


# ---------------------------------------------------------------------------
# Config: evolution section
# ---------------------------------------------------------------------------


class TestEvolutionConfig:
    def test_default_config_has_evolution(self):
        from polyharness.config import PolyHarnessConfig

        config = PolyHarnessConfig()
        assert config.evolution.mode == "batch"
        assert config.evolution.max_iterations == 3
        assert config.evolution.auto_apply is False
        assert config.evolution.trigger.strategy == "manual"

    def test_config_roundtrip_yaml(self, tmp_path: Path):
        from polyharness.config import PolyHarnessConfig

        config = PolyHarnessConfig()
        config.evolution.mode = "online"
        config.evolution.trigger.strategy = "degradation"

        path = tmp_path / "config.yaml"
        config.to_yaml(path)

        loaded = PolyHarnessConfig.from_yaml(path)
        assert loaded.evolution.mode == "online"
        assert loaded.evolution.trigger.strategy == "degradation"
        assert loaded.evolution.max_iterations == 3
