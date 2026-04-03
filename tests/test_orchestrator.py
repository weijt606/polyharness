"""Tests for the Orchestrator — using a mock Proposer + simple evaluator."""

import json

from poly_harness.evaluator import BaseEvaluator, EvalResult
from poly_harness.orchestrator import Orchestrator, SearchResult
from poly_harness.proposer.base import BaseProposer
from poly_harness.workspace import Workspace


class MockProposer(BaseProposer):
    """A mock proposer that makes deterministic changes."""

    def __init__(self):
        self.call_count = 0

    def propose(self, workspace_root, candidate_dir, iteration, parent):
        self.call_count += 1
        # Write a slightly modified harness each time
        harness = candidate_dir / "harness.py"
        harness.write_text(f"# iteration {iteration}\nSCORE_HINT = {0.3 + iteration * 0.1}\n")
        return {"changes_summary": f"Mock changes for iteration {iteration}"}


class MockEvaluator(BaseEvaluator):
    """A mock evaluator that reads a score hint from the harness."""

    def evaluate(self, candidate_dir, tasks):
        harness = candidate_dir / "harness.py"
        score = 0.3  # default
        if harness.exists():
            for line in harness.read_text().splitlines():
                if line.startswith("SCORE_HINT"):
                    score = float(line.split("=")[1].strip())
        return EvalResult(
            overall_score=min(score, 1.0),
            task_scores={"mock_task": min(score, 1.0)},
        )


def _setup_workspace(tmp_path) -> Workspace:
    ws = Workspace.init(tmp_path / "ws")
    # Create a simple base harness
    (ws.base_harness_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
    return ws


def test_orchestrator_runs(tmp_path):
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 3
    config.search.early_stop_patience = 10

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    result = orch.run()

    assert isinstance(result, SearchResult)
    assert result.total_iterations >= 3
    assert result.best_score > 0.3


def test_orchestrator_early_stop(tmp_path):
    """Proposer always returns same score → should early stop."""

    class ConstantProposer(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
            return {"changes_summary": "no change"}

    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 20
    config.search.early_stop_patience = 3

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=ConstantProposer(),
        evaluator=MockEvaluator(),
    )
    result = orch.run()

    # Should stop early well before 20 iterations
    assert result.total_iterations < 10


def test_orchestrator_creates_files(tmp_path):
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 10

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    orch.run()

    # Check workspace files were created
    assert (ws.candidate_path(0) / "score.json").exists()
    assert (ws.candidate_path(1) / "score.json").exists()
    assert (ws.candidate_path(2) / "score.json").exists()
    assert ws.search_log_path.stat().st_size > 0

    # Check leaderboard
    leaderboard = ws.summary_dir / "leaderboard.json"
    assert leaderboard.exists()
    entries = json.loads(leaderboard.read_text())
    assert len(entries) >= 3


def test_orchestrator_tournament_selection(tmp_path):
    """Tournament selection should pick from random sample of candidates."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 5
    config.search.early_stop_patience = 10
    config.search.parent_selection = "tournament"

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    result = orch.run()

    assert isinstance(result, SearchResult)
    assert result.total_iterations >= 5
    assert result.best_score > 0.3


def test_orchestrator_resume(tmp_path):
    """Resume should continue from where a previous run left off."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 3
    config.search.early_stop_patience = 10

    # First run: 3 iterations
    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    result1 = orch.run()
    assert result1.total_iterations == 3

    # Resume run with 5 total iterations (should run 2 more)
    config2 = ws.load_config()
    config2.search.max_iterations = 5
    config2.search.early_stop_patience = 10

    orch2 = Orchestrator(
        workspace=ws,
        config=config2,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    result2 = orch2.run(resume=True)

    # Should have completed up to iteration 5
    assert result2.total_iterations >= 4
    assert result2.best_score >= result1.best_score


def test_orchestrator_resume_already_complete(tmp_path):
    """Resume when all iterations done should return immediately."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 10

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    orch.run()

    # Resume with same max_iterations
    orch2 = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    result = orch2.run(resume=True)
    assert result.best_score > 0


def test_orchestrator_error_recovery(tmp_path):
    """Orchestrator should skip failing iterations and continue."""

    class FailingProposer(BaseProposer):
        def __init__(self):
            self.call_count = 0

        def propose(self, workspace_root, candidate_dir, iteration, parent):
            self.call_count += 1
            if self.call_count == 1:
                raise RuntimeError("Simulated proposer failure")
            # Subsequent calls succeed
            (candidate_dir / "harness.py").write_text(f"SCORE_HINT = {0.5 + iteration * 0.05}\n")
            return {"changes_summary": f"iteration {iteration}"}

    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 3
    config.search.early_stop_patience = 10

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=FailingProposer(),
        evaluator=MockEvaluator(),
    )
    # Should not crash — iter_1 fails, iter_2 and iter_3 succeed
    result = orch.run()
    assert result.best_score > 0
