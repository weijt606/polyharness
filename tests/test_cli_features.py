"""Tests for new CLI features: verbose/quiet, dry-run, clean, progress bar."""

import json

import pytest
from click.testing import CliRunner

from poly_harness.cli import main
from poly_harness.workspace import Workspace


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal initialized workspace."""
    ws = Workspace.init(tmp_path / "ws", agent_backend="local")
    (ws.base_harness_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
    return ws


@pytest.fixture
def runner():
    return CliRunner()


# --- Global flags ---


def test_help_shows_verbose_quiet(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--verbose" in result.output or "-v" in result.output
    assert "--quiet" in result.output or "-q" in result.output


def test_quiet_flag_accepted(runner, workspace):
    result = runner.invoke(main, ["-q", "status", "--workspace", str(workspace.root)])
    # Should not crash (workspace has no log yet, so it will error about missing data, but flag should parse)
    assert result.exit_code in (0, 1)


def test_verbose_flag_accepted(runner, workspace):
    result = runner.invoke(main, ["-v", "status", "--workspace", str(workspace.root)])
    assert result.exit_code in (0, 1)


# --- Dry run ---


def test_run_dry_run_flag_in_help(runner):
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_run_dry_run(runner, workspace):
    """Dry run should evaluate base only and return quickly."""
    # Write a simple evaluate.py
    eval_script = workspace.root / "evaluate.py"
    eval_script.write_text(
        'import json, sys\n'
        'print(json.dumps({"overall_score": 0.5, "task_scores": {"t1": 0.5}}))\n'
    )
    result = runner.invoke(main, ["run", "--workspace", str(workspace.root), "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output or "base" in result.output.lower()


# --- Clean command ---


def test_clean_help(runner):
    result = runner.invoke(main, ["clean", "--help"])
    assert result.exit_code == 0
    assert "--keep-best" in result.output
    assert "--yes" in result.output


def test_clean_empty_workspace(runner, workspace):
    """Clean on workspace with no candidates should say nothing to clean."""
    result = runner.invoke(main, ["clean", "--workspace", str(workspace.root), "-y"])
    assert result.exit_code == 0
    assert "Nothing to clean" in result.output


def test_clean_removes_candidates(runner, workspace):
    """Clean should remove candidate directories."""
    # Create some fake candidate dirs
    for i in range(3):
        d = workspace.candidates_dir / f"iter_{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "harness.py").write_text(f"# iter {i}\n")

    result = runner.invoke(main, ["clean", "--workspace", str(workspace.root), "-y"])
    assert result.exit_code == 0
    assert "Cleaned" in result.output
    # All candidate dirs should be gone
    remaining = list(workspace.candidates_dir.iterdir())
    assert len([d for d in remaining if d.is_dir()]) == 0


def test_clean_keep_best(runner, workspace):
    """Clean --keep-best should preserve the best candidate."""
    # Create fake candidates + a search log with iter_1 as best
    for i in range(3):
        d = workspace.candidates_dir / f"iter_{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "harness.py").write_text(f"# iter {i}\n")
        (d / "score.json").write_text(json.dumps({"overall_score": 0.3 + i * 0.1}))

    # Write search log entries so best_iteration can be determined
    from poly_harness.search_log import SearchLog
    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={})
    log.append(iteration=1, parent=0, score=0.5, task_scores={})
    log.append(iteration=2, parent=0, score=0.4, task_scores={})

    result = runner.invoke(main, ["clean", "--workspace", str(workspace.root), "--keep-best", "-y"])
    assert result.exit_code == 0

    # iter_1 (best) should be preserved
    remaining = [d.name for d in workspace.candidates_dir.iterdir() if d.is_dir()]
    assert "iter_1" in remaining
    assert len(remaining) == 1


# --- Orchestrator dry-run ---


def test_orchestrator_dry_run(tmp_path):
    """Orchestrator with max_iterations=0 should return after base eval."""
    from poly_harness.evaluator import BaseEvaluator, EvalResult
    from poly_harness.orchestrator import Orchestrator, SearchResult
    from poly_harness.proposer.base import BaseProposer

    class NeverCalled(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            raise AssertionError("Proposer should not be called in dry run")

    class SimpleEval(BaseEvaluator):
        def evaluate(self, candidate_dir, tasks):
            return EvalResult(overall_score=0.42, task_scores={"t": 0.42})

    ws = Workspace.init(tmp_path / "ws")
    (ws.base_harness_dir / "harness.py").write_text("pass\n")
    config = ws.load_config()
    config.search.max_iterations = 0

    orch = Orchestrator(workspace=ws, config=config, proposer=NeverCalled(), evaluator=SimpleEval())
    result = orch.run()

    assert isinstance(result, SearchResult)
    assert result.best_iteration == 0
    assert result.best_score == pytest.approx(0.42)
    assert result.total_iterations == 0


# --- Status enhancements ---


def test_status_shows_elapsed(runner, workspace):
    """Status should display elapsed time when log has timestamps."""
    import json as _json

    entries = [
        {"iteration": 0, "parent": None, "score": 0.3, "best_so_far": 0.3,
         "timestamp": "2025-01-01T00:00:00", "task_scores": {}},
        {"iteration": 1, "parent": 0, "score": 0.5, "best_so_far": 0.5,
         "timestamp": "2025-01-01T00:05:30", "task_scores": {}},
    ]
    with open(workspace.search_log_path, "w") as f:
        for e in entries:
            f.write(_json.dumps(e) + "\n")

    # Create candidate dirs so workspace looks valid
    for i in range(2):
        d = workspace.candidates_dir / f"iter_{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "score.json").write_text(json.dumps({"overall_score": 0.3 + i * 0.2}))

    result = runner.invoke(main, ["status", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    # Should contain elapsed time info
    assert "Elapsed" in result.output or "elapsed" in result.output or "5m" in result.output


# --- Log delta column ---


def test_log_shows_delta(runner, workspace):
    """ph log should display delta column."""
    from poly_harness.search_log import SearchLog

    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={})
    log.append(iteration=1, parent=0, score=0.5, task_scores={})
    log.append(iteration=2, parent=1, score=0.4, task_scores={})

    result = runner.invoke(main, ["log", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    # Delta column header or values should appear
    assert "Δ" in result.output or "delta" in result.output.lower() or "+0.2" in result.output


# --- ph run --resume ---


def test_run_resume_flag_in_help(runner):
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--resume" in result.output


# --- ph run --backend ---


def test_run_backend_flag_in_help(runner):
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--backend" in result.output


# --- ph config show ---


def test_config_show(runner, workspace):
    result = runner.invoke(main, ["config", "show", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "proposer" in result.output
    assert "evaluator" in result.output


# --- ph config set ---


def test_config_set(runner, workspace):
    result = runner.invoke(main, ["config", "set", "search.max_iterations", "30",
                                  "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "30" in result.output

    # Verify the change persisted
    config = workspace.load_config()
    assert config.search.max_iterations == 30


def test_config_set_invalid(runner, workspace):
    """Setting an invalid value should fail with an error."""
    result = runner.invoke(main, ["config", "set", "search.max_iterations", "-5",
                                  "--workspace", str(workspace.root)])
    assert result.exit_code != 0


def test_config_set_backend(runner, workspace):
    result = runner.invoke(main, ["config", "set", "proposer.backend", "claude-code",
                                  "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    config = workspace.load_config()
    assert config.proposer.backend == "claude-code"


# --- ph diff ---


def test_diff_help(runner):
    result = runner.invoke(main, ["diff", "--help"])
    assert result.exit_code == 0
    assert "ITERATION" in result.output


def test_diff_shows_comparison(runner, workspace):
    """ph diff should compare base vs given iteration."""
    for i in range(2):
        d = workspace.candidates_dir / f"iter_{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "score.json").write_text(json.dumps({
            "overall_score": 0.3 + i * 0.2,
            "task_scores": {"t1": 0.3 + i * 0.2},
        }))
        (d / "harness.py").write_text(f"# iteration {i}\n")

    from poly_harness.search_log import SearchLog
    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={"t1": 0.3})
    log.append(iteration=1, parent=0, score=0.5, task_scores={"t1": 0.5})

    result = runner.invoke(main, ["diff", "1", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "iter_0" in result.output
    assert "iter_1" in result.output


# --- ph run --strategy ---


def test_run_strategy_flag_in_help(runner):
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--strategy" in result.output


# --- ph leaderboard ---


def test_leaderboard_help(runner):
    result = runner.invoke(main, ["leaderboard", "--help"])
    assert result.exit_code == 0
    assert "--top" in result.output
    assert "--tasks" in result.output


def test_leaderboard_basic(runner, workspace):
    from poly_harness.search_log import SearchLog
    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={"t1": 0.3})
    log.append(iteration=1, parent=0, score=0.7, task_scores={"t1": 0.7})
    log.append(iteration=2, parent=0, score=0.5, task_scores={"t1": 0.5})

    result = runner.invoke(main, ["leaderboard", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "iter_1" in result.output
    assert "★" in result.output


def test_leaderboard_top_n(runner, workspace):
    from poly_harness.search_log import SearchLog
    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={})
    log.append(iteration=1, parent=0, score=0.7, task_scores={})
    log.append(iteration=2, parent=0, score=0.5, task_scores={})

    result = runner.invoke(main, ["leaderboard", "--workspace", str(workspace.root), "-n", "2"])
    assert result.exit_code == 0
    # Rank 1 and 2 shown, but not necessarily rank 3 (iter_0 at 0.3)
    assert "iter_1" in result.output


def test_leaderboard_with_tasks(runner, workspace):
    from poly_harness.search_log import SearchLog
    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={"task_a": 0.2, "task_b": 0.4})
    log.append(iteration=1, parent=0, score=0.7, task_scores={"task_a": 0.8, "task_b": 0.6})

    result = runner.invoke(main, ["leaderboard", "--workspace", str(workspace.root), "--tasks"])
    assert result.exit_code == 0
    assert "task_a" in result.output
    assert "task_b" in result.output


# --- ph trace ---


def test_trace_help(runner):
    result = runner.invoke(main, ["trace", "--help"])
    assert result.exit_code == 0
    assert "ITERATION" in result.output


def test_trace_shows_output(runner, workspace):
    """ph trace should display stdout/stderr from evaluation."""
    cand = workspace.candidates_dir / "iter_1"
    cand.mkdir(parents=True, exist_ok=True)
    (cand / "score.json").write_text(json.dumps({"overall_score": 0.5}))
    traces = cand / "traces"
    traces.mkdir()
    (traces / "default.stdout").write_text("Hello from evaluator\n")
    (traces / "default.stderr").write_text("Warning: something\n")
    (traces / "default.exitcode").write_text("0\n")
    (traces / "default.metrics.json").write_text(json.dumps({"score": 0.5}))

    result = runner.invoke(main, ["trace", "1", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "Hello from evaluator" in result.output
    assert "Warning: something" in result.output


def test_trace_no_traces(runner, workspace):
    cand = workspace.candidates_dir / "iter_1"
    cand.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(main, ["trace", "1", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "No traces" in result.output


def test_trace_task_filter(runner, workspace):
    """--task should filter to a specific task."""
    cand = workspace.candidates_dir / "iter_1"
    cand.mkdir(parents=True, exist_ok=True)
    traces = cand / "traces"
    traces.mkdir()
    (traces / "task_a.stdout").write_text("output A\n")
    (traces / "task_b.stdout").write_text("output B\n")
    (traces / "task_a.exitcode").write_text("0\n")
    (traces / "task_b.exitcode").write_text("0\n")

    result = runner.invoke(main, ["trace", "1", "--workspace", str(workspace.root), "--task", "task_a"])
    assert result.exit_code == 0
    assert "output A" in result.output
    # task_b should NOT appear
    assert "output B" not in result.output


# --- ph report ---


def test_report_help(runner):
    result = runner.invoke(main, ["report", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.output


def test_report_generates_markdown(runner, workspace):
    import json as _json

    entries = [
        {"iteration": 0, "parent": None, "score": 0.3, "best_so_far": 0.3,
         "timestamp": "2025-01-01T00:00:00", "task_scores": {"t1": 0.3}},
        {"iteration": 1, "parent": 0, "score": 0.5, "best_so_far": 0.5,
         "timestamp": "2025-01-01T00:03:00", "task_scores": {"t1": 0.5}},
        {"iteration": 2, "parent": 1, "score": 0.8, "best_so_far": 0.8,
         "timestamp": "2025-01-01T00:06:00", "task_scores": {"t1": 0.8}},
    ]
    with open(workspace.search_log_path, "w") as f:
        for e in entries:
            f.write(_json.dumps(e) + "\n")

    result = runner.invoke(main, ["report", "--workspace", str(workspace.root)])
    assert result.exit_code == 0
    assert "Report written" in result.output

    report_path = workspace.summary_dir / "report.md"
    assert report_path.exists()
    content = report_path.read_text()
    assert "# PolyHarness Optimization Report" in content
    assert "iter_2" in content
    assert "0.8000" in content
    assert "Score Trend" in content


def test_report_custom_output(runner, workspace, tmp_path):
    from poly_harness.search_log import SearchLog
    log = SearchLog(workspace.search_log_path)
    log.append(iteration=0, parent=None, score=0.3, task_scores={})
    log.append(iteration=1, parent=0, score=0.5, task_scores={})

    out_path = tmp_path / "custom_report.md"
    result = runner.invoke(main, ["report", "--workspace", str(workspace.root), "-o", str(out_path)])
    assert result.exit_code == 0
    assert out_path.exists()
    assert "PolyHarness" in out_path.read_text()
