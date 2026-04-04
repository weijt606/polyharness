"""Tests for the 'ph log' command (tree and flat views)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from polyharness.cli import main


def _make_workspace(tmp_path, entries=None):
    """Create a workspace with search log entries."""
    ws = tmp_path / "ws"
    (ws / "base_harness").mkdir(parents=True)
    (ws / "candidates").mkdir()
    (ws / "summary").mkdir()
    (ws / "config.yaml").write_text("search:\n  max_iterations: 10\n")

    if entries is None:
        entries = [
            {"iteration": 0, "parent": None, "score": 0.5, "best_so_far": 0.5},
            {"iteration": 1, "parent": 0, "score": 0.7, "best_so_far": 0.7},
            {"iteration": 2, "parent": 0, "score": 0.6, "best_so_far": 0.7},
            {"iteration": 3, "parent": 1, "score": 0.9, "best_so_far": 0.9},
            {"iteration": 4, "parent": 1, "score": 0.8, "best_so_far": 0.9},
        ]

    with (ws / "search_log.jsonl").open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return ws


def test_log_tree_default(tmp_path):
    """Default output shows a tree with parent→child relationships."""
    ws = _make_workspace(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "iter_0" in result.output
    assert "iter_3" in result.output
    assert "0.9000" in result.output


def test_log_tree_marks_best(tmp_path):
    """Best candidate is marked with a star."""
    ws = _make_workspace(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    # iter_3 is best (0.9) — should have star marker
    assert "★" in result.output


def test_log_flat_mode(tmp_path):
    """--flat shows a table instead of a tree."""
    ws = _make_workspace(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--flat", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "Search Log" in result.output
    assert "iter_0" in result.output
    assert "iter_4" in result.output


def test_log_empty_workspace(tmp_path):
    """No iterations → helpful message."""
    ws = _make_workspace(tmp_path, entries=[])
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--workspace", str(ws)])
    assert result.exit_code == 0
    assert "No iterations" in result.output


def test_log_summary_line(tmp_path):
    """Summary shows iteration count and best score."""
    ws = _make_workspace(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "5 iterations" in result.output
    assert "iter_3" in result.output


def test_log_branching_tree(tmp_path):
    """Tree handles branching correctly (multiple children from same parent)."""
    entries = [
        {"iteration": 0, "parent": None, "score": 0.3, "best_so_far": 0.3},
        {"iteration": 1, "parent": 0, "score": 0.5, "best_so_far": 0.5},
        {"iteration": 2, "parent": 0, "score": 0.4, "best_so_far": 0.5},
        {"iteration": 3, "parent": 0, "score": 0.6, "best_so_far": 0.6},
    ]
    ws = _make_workspace(tmp_path, entries)
    runner = CliRunner()
    result = runner.invoke(main, ["log", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    # All three children of iter_0 should appear
    assert "iter_1" in result.output
    assert "iter_2" in result.output
    assert "iter_3" in result.output
