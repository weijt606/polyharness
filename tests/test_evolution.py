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

    def test_wrap_passes_dashed_agent_args(self, runner: CliRunner, store_dir: Path):
        """Agent flags like `-p`/`--flag` must be forwarded, not parsed by wrap.

        Regression: README examples (`ph wrap claude -p "..."`) used to fail
        with `No such option: -p`.
        """
        result = runner.invoke(
            main, ["wrap", "--store", str(store_dir), "echo", "-n", "--flag", "hello"]
        )
        assert result.exit_code == 0
        assert "No such option" not in result.output
        traces = list(store_dir.iterdir())
        meta = json.loads((traces[0] / "meta.json").read_text())
        assert meta["command"] == ["echo", "-n", "--flag", "hello"]

    def test_wrap_command_not_found(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(
            main, ["wrap", "--store", str(store_dir), "nonexistent_cmd_xyz"]
        )
        assert result.exit_code == 127

    def test_wrap_auto_evolve_flag_accepted(self, runner: CliRunner, store_dir: Path):
        result = runner.invoke(
            main,
            ["wrap", "--store", str(store_dir), "--auto-evolve", "echo", "hi"],
        )
        assert "hi" in result.output
        assert "trace recorded" in result.output

    def test_wrap_auto_evolve_skips_without_workspace(
        self, runner: CliRunner, store_dir: Path, tmp_path: Path, monkeypatch
    ):
        """auto-evolve silently skips when no .ph_workspace exists."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            main,
            ["wrap", "--store", str(store_dir), "--auto-evolve", "echo", "test"],
        )
        assert "trace recorded" in result.output
        # Should NOT crash or mention evolution
        assert "triggering auto-evolution" not in result.output

    def test_wrap_auto_evolve_shows_progress(
        self, runner: CliRunner, store_dir: Path, tmp_path: Path
    ):
        """auto-evolve shows N/threshold progress when below threshold."""
        from polyharness.workspace import Workspace

        ws = Workspace.init(tmp_path / "ws", agent_backend="local")
        # Set accumulate_count=5, so 1 trace won't trigger
        import yaml

        config_path = ws.root / "config.yaml"
        cfg = yaml.safe_load(config_path.read_text())
        cfg["evolution"] = {"trigger": {"strategy": "accumulate", "accumulate_count": 5}}
        config_path.write_text(yaml.dump(cfg))

        result = runner.invoke(
            main,
            [
                "wrap",
                "--store", str(store_dir),
                "--auto-evolve",
                "--workspace", str(ws.root),
                "echo", "test",
            ],
        )
        assert "1/5" in result.output

    def test_wrap_auto_evolve_triggers_when_threshold_met(
        self, runner: CliRunner, store_dir: Path, tmp_path: Path
    ):
        """auto-evolve triggers evolution when enough traces accumulate."""
        from polyharness.workspace import Workspace

        ws = Workspace.init(tmp_path / "ws", agent_backend="local")
        import yaml

        config_path = ws.root / "config.yaml"
        cfg = yaml.safe_load(config_path.read_text())
        cfg["evolution"] = {"trigger": {"strategy": "accumulate", "accumulate_count": 2}}
        config_path.write_text(yaml.dump(cfg))

        # Record 1st trace — should not trigger
        runner.invoke(
            main,
            [
                "wrap",
                "--store", str(store_dir),
                "--auto-evolve",
                "--workspace", str(ws.root),
                "echo", "first",
            ],
        )
        # Record 2nd trace — should trigger
        result = runner.invoke(
            main,
            [
                "wrap",
                "--store", str(store_dir),
                "--auto-evolve",
                "--workspace", str(ws.root),
                "echo", "second",
            ],
        )
        assert "triggering auto-evolution" in result.output.lower()


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


# ---------------------------------------------------------------------------
# ph shell-hook
# ---------------------------------------------------------------------------


class TestShellHook:
    def test_shell_hook_help(self, runner: CliRunner):
        result = runner.invoke(main, ["shell-hook", "--help"])
        assert result.exit_code == 0
        assert "auto-wrap" in result.output.lower()

    def test_install_creates_hook(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing config\n")
        result = runner.invoke(main, ["shell-hook", "install", "--rc", str(rc)])
        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        content = rc.read_text()
        assert "polyharness shell-hook" in content
        assert "_ph_wrap_run" in content

    def test_install_idempotent(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing config\n")
        runner.invoke(main, ["shell-hook", "install", "--rc", str(rc)])
        result = runner.invoke(main, ["shell-hook", "install", "--rc", str(rc)])
        assert result.exit_code == 0
        assert "already installed" in result.output.lower()
        # Should only appear once
        content = rc.read_text()
        assert content.count("polyharness shell-hook") == 2  # start + end markers

    def test_uninstall_removes_hook(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing config\n")
        runner.invoke(main, ["shell-hook", "install", "--rc", str(rc)])
        result = runner.invoke(main, ["shell-hook", "uninstall", "--rc", str(rc)])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()
        content = rc.read_text()
        assert "polyharness shell-hook" not in content

    def test_uninstall_no_hook(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# clean config\n")
        result = runner.invoke(main, ["shell-hook", "uninstall", "--rc", str(rc)])
        assert result.exit_code == 0
        assert "no hook found" in result.output.lower()

    def test_status_not_installed(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# clean\n")
        result = runner.invoke(main, ["shell-hook", "status", "--rc", str(rc)])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_status_installed(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing\n")
        runner.invoke(main, ["shell-hook", "install", "--rc", str(rc)])
        result = runner.invoke(main, ["shell-hook", "status", "--rc", str(rc)])
        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        assert "claude" in result.output.lower()

    def test_uninstall_preserves_surrounding(self, runner: CliRunner, tmp_path: Path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# before\nexport FOO=1\n")
        runner.invoke(main, ["shell-hook", "install", "--rc", str(rc)])
        # Add content after the hook
        with open(rc, "a") as f:
            f.write("# after\nexport BAR=2\n")
        runner.invoke(main, ["shell-hook", "uninstall", "--rc", str(rc)])
        content = rc.read_text()
        assert "FOO=1" in content
        assert "BAR=2" in content
        assert "polyharness" not in content
