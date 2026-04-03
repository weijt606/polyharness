"""Tests for the 'ph export' command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from poly_harness.cli import main


def _make_workspace(tmp_path):
    """Create a minimal workspace with two iterations."""
    ws = tmp_path / "ws"
    (ws / "base_harness").mkdir(parents=True)
    (ws / "candidates").mkdir()
    (ws / "summary").mkdir()

    # config
    (ws / "config.yaml").write_text("search:\n  max_iterations: 3\n")

    # search log
    log_entries = [
        {"iteration": 0, "score": 0.6, "parent": None, "best_so_far": 0.6},
        {"iteration": 1, "score": 0.9, "parent": 0, "best_so_far": 0.9},
    ]
    with (ws / "search_log.jsonl").open("w") as f:
        for entry in log_entries:
            f.write(json.dumps(entry) + "\n")

    # iter_0
    iter0 = ws / "candidates" / "iter_0"
    iter0.mkdir()
    (iter0 / "harness.py").write_text("# v0\n")
    (iter0 / "score.json").write_text(json.dumps({"overall_score": 0.6, "task_scores": {}}))
    (iter0 / "metadata.json").write_text(json.dumps({"iteration": 0}))
    (iter0 / "traces").mkdir()
    (iter0 / "traces" / "trace.txt").write_text("trace data")

    # iter_1
    iter1 = ws / "candidates" / "iter_1"
    iter1.mkdir()
    (iter1 / "harness.py").write_text("# v1\n")
    (iter1 / "helper.py").write_text("# helper\n")
    (iter1 / "score.json").write_text(json.dumps({"overall_score": 0.9, "task_scores": {}}))
    (iter1 / "metadata.json").write_text(json.dumps({"iteration": 1}))
    (iter1 / "traces").mkdir()
    (iter1 / "traces" / "trace.txt").write_text("trace data 1")

    return ws


def test_export_best_default(tmp_path):
    """Export best candidate (iter_1) by default, excluding meta files."""
    ws = _make_workspace(tmp_path)
    dest = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(main, ["export", str(dest), "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "iter_1" in result.output
    # Code files copied
    assert (dest / "harness.py").exists()
    assert (dest / "helper.py").exists()
    # Meta files excluded by default
    assert not (dest / "score.json").exists()
    assert not (dest / "metadata.json").exists()
    assert not (dest / "traces").exists()


def test_export_specific_iteration(tmp_path):
    """Export a specific iteration with --iteration flag."""
    ws = _make_workspace(tmp_path)
    dest = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main, ["export", str(dest), "--workspace", str(ws), "--iteration", "0"]
    )
    assert result.exit_code == 0, result.output
    assert "iter_0" in result.output
    assert (dest / "harness.py").read_text() == "# v0\n"
    # Only 1 file (no helper.py in iter_0)
    assert not (dest / "helper.py").exists()


def test_export_include_meta(tmp_path):
    """--include-meta copies score.json, metadata.json, and traces/."""
    ws = _make_workspace(tmp_path)
    dest = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main, ["export", str(dest), "--workspace", str(ws), "--include-meta"]
    )
    assert result.exit_code == 0, result.output
    assert (dest / "score.json").exists()
    assert (dest / "metadata.json").exists()
    assert (dest / "traces" / "trace.txt").exists()


def test_export_missing_iteration(tmp_path):
    """Error when requested iteration doesn't exist."""
    ws = _make_workspace(tmp_path)
    dest = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main, ["export", str(dest), "--workspace", str(ws), "--iteration", "99"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_export_no_candidates(tmp_path):
    """Error when workspace has no iterations."""
    ws = tmp_path / "ws"
    (ws / "base_harness").mkdir(parents=True)
    (ws / "candidates").mkdir()
    (ws / "summary").mkdir()
    (ws / "config.yaml").write_text("search:\n  max_iterations: 3\n")
    (ws / "search_log.jsonl").touch()

    dest = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(main, ["export", str(dest), "--workspace", str(ws)])
    assert result.exit_code != 0
    assert "No candidates" in result.output


def test_export_creates_target_dir(tmp_path):
    """Target directory is created if it doesn't exist."""
    ws = _make_workspace(tmp_path)
    dest = tmp_path / "nested" / "deep" / "out"
    runner = CliRunner()
    result = runner.invoke(main, ["export", str(dest), "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert dest.exists()
    assert (dest / "harness.py").exists()
