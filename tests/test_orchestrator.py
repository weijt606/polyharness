"""Tests for the Orchestrator — using a mock Proposer + simple evaluator."""

import json

from polyharness.evaluator import BaseEvaluator, EvalResult
from polyharness.orchestrator import Orchestrator, SearchResult
from polyharness.proposer.base import BaseProposer
from polyharness.workspace import Workspace


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


def test_orchestrator_pareto_selection(tmp_path):
    """Pareto selection should run end-to-end and find improvements."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 5
    config.search.early_stop_patience = 10
    config.search.parent_selection = "pareto"

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


def test_pareto_select_picks_per_task_winner(tmp_path):
    """A per-task specialist should be selectable even when not best overall.

    iter_0 is mediocre on every task; iter_1 and iter_2 each win exactly one
    task. 'best' selection would never branch from a specialist, but the
    Pareto frontier keeps them alive.
    """
    import random

    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )

    # Same overall score (0.5) but different per-task profiles.
    orch.search_log.append(0, None, 0.5, {"A": 0.5, "B": 0.5})
    orch.search_log.append(1, 0, 0.5, {"A": 0.9, "B": 0.1})  # wins task A
    orch.search_log.append(2, 0, 0.5, {"A": 0.1, "B": 0.9})  # wins task B

    random.seed(0)
    picks = {orch._pareto_select() for _ in range(100)}

    # iter_0 wins no task → must never be chosen; both specialists reachable.
    assert 0 not in picks
    assert picks == {1, 2}


def test_pareto_select_falls_back_without_task_scores(tmp_path):
    """Without per-task scores, Pareto selection degrades to best-overall."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )
    orch.search_log.append(0, None, 0.4, {})
    orch.search_log.append(1, 0, 0.7, {})

    assert orch._pareto_select() == 1  # == best_iteration


def test_novelty_filter_skips_duplicate(tmp_path):
    """A proposer that always emits identical code should get its candidates
    rejected (and their evaluation skipped) when the novelty filter is on."""

    class ConstantProposer(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
            return {"changes_summary": "no change"}

    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 5
    config.search.early_stop_patience = 3
    config.search.novelty_filter = True
    config.search.novelty_threshold = 0.97
    config.search.novelty_max_retries = 1

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=ConstantProposer(),
        evaluator=MockEvaluator(),
    )
    orch.run()

    # Only the base (iter_0) is evaluated; every later duplicate is skipped,
    # so it never gets appended to the search log.
    logged = [e.iteration for e in orch.search_log.entries]
    assert logged == [0]
    # And the skipped candidate dir is cleaned up (no dangling copy).
    assert not ws.candidate_path(1).exists()


def test_novelty_filter_allows_novel(tmp_path):
    """Distinct candidates should pass the novelty gate and be evaluated."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 3
    config.search.early_stop_patience = 10
    config.search.novelty_filter = True
    config.search.novelty_threshold = 0.97

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),  # writes a distinct harness each iteration
        evaluator=MockEvaluator(),
    )
    result = orch.run()

    assert result.best_score > 0.3
    for i in (1, 2, 3):
        assert (ws.candidate_path(i) / "score.json").exists()


def test_max_similarity_detects_identical(tmp_path):
    """_max_similarity returns ~1.0 for identical code, low for distinct code."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),
        evaluator=MockEvaluator(),
    )

    # iter_0 = copy of base ("SCORE_HINT = 0.3")
    ws.prepare_candidate(0, parent=None)
    orch.search_log.append(0, None, 0.3, {"mock_task": 0.3})

    # An identical candidate scores ~1.0 similarity against iter_0.
    dup = ws.prepare_candidate(1, parent=0)
    (dup / "harness.py").write_text("SCORE_HINT = 0.3\n")
    assert orch._max_similarity(1, dup) > 0.97

    # A clearly different candidate scores low.
    novel = ws.prepare_candidate(2, parent=0)
    (novel / "harness.py").write_text(
        "import math\n\ndef solve(x):\n    return math.sqrt(x) * 42 + len(str(x))\n"
    )
    assert orch._max_similarity(2, novel) < 0.97


def test_orchestrator_ensemble_bandit(tmp_path):
    """The bandit should favor the backend that produces improvements."""

    class HighProposer(BaseProposer):
        """Improves every iteration."""

        def propose(self, workspace_root, candidate_dir, iteration, parent):
            score = min(0.4 + iteration * 0.1, 1.0)
            (candidate_dir / "harness.py").write_text(f"SCORE_HINT = {score}\n")
            return {"changes_summary": "high"}

    class LowProposer(BaseProposer):
        """Never improves over the base."""

        def propose(self, workspace_root, candidate_dir, iteration, parent):
            (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
            return {"changes_summary": "low"}

    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 6
    config.search.early_stop_patience = 20
    config.proposer.ensemble = ["local", "api"]  # valid backend names

    orch = Orchestrator(
        workspace=ws,
        config=config,
        # Inject mocks keyed by backend name so no real CLIs/API are touched.
        proposers={"local": HighProposer(), "api": LowProposer()},
        evaluator=MockEvaluator(),
    )
    result = orch.run()

    assert orch.bandit is not None
    stats = orch.bandit.stats()
    # Both arms are tried at least once (cold start), and the improving backend
    # ("local"=HighProposer) earns a perfect improve-rate while the other earns 0.
    assert stats["local"]["pulls"] >= 1
    assert stats["api"]["pulls"] >= 1
    assert stats["local"]["mean_reward"] == 1.0
    assert stats["api"]["mean_reward"] == 0.0
    assert stats["local"]["pulls"] >= stats["api"]["pulls"]
    assert result.best_score >= 0.9
    # The winning candidate records which backend produced it.
    best_meta = json.loads(
        (ws.candidate_path(result.best_iteration) / "metadata.json").read_text()
    )
    assert best_meta["proposer_backend"] == "local"


def test_ensemble_disabled_when_proposer_injected(tmp_path):
    """An explicit single proposer wins over an ensemble config (back-compat)."""
    ws = _setup_workspace(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 10
    config.proposer.ensemble = ["local", "api"]

    orch = Orchestrator(
        workspace=ws,
        config=config,
        proposer=MockProposer(),  # explicit → disables the bandit
        evaluator=MockEvaluator(),
    )
    assert orch.bandit is None
    result = orch.run()
    assert result.best_score > 0.3


def test_seed_makes_search_reproducible(tmp_path):
    """Same seed + randomized strategy → identical parent-selection trajectory."""

    def run_once(path):
        ws = Workspace.init(path)
        (ws.base_harness_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
        config = ws.load_config()
        config.search.max_iterations = 6
        config.search.early_stop_patience = 20
        config.search.parent_selection = "tournament"
        config.search.seed = 42
        orch = Orchestrator(
            workspace=ws,
            config=config,
            proposer=MockProposer(),
            evaluator=MockEvaluator(),
        )
        orch.run()
        return [e.parent for e in orch.search_log.entries]

    assert run_once(tmp_path / "a") == run_once(tmp_path / "b")


class PerTaskEvaluator(BaseEvaluator):
    """Evaluator that scores by task name and records which task lists it ran."""

    def __init__(self, task_scores):
        self.task_scores = task_scores
        self.calls: list[list[str]] = []

    def evaluate(self, candidate_dir, tasks):
        from pathlib import Path

        stems = [Path(t).stem for t in tasks]
        self.calls.append(stems)
        ts = {s: self.task_scores.get(s, 0.0) for s in stems}
        overall = sum(ts.values()) / len(ts) if ts else 0.0
        return EvalResult(overall_score=overall, task_scores=ts)


def _cascade_config(ws, **overrides):
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 10
    config.evaluator.tasks = ["t1.json", "t2.json", "t3.json", "t4.json"]
    config.evaluator.cascade = True
    config.evaluator.cascade_stage1 = 2
    config.evaluator.cascade_threshold = 0.5
    for k, v in overrides.items():
        setattr(config.evaluator, k, v)
    return config


def test_cascade_gates_weak_candidate(tmp_path):
    """A candidate failing stage 1 should never trigger stage-2 evaluation."""
    ws = _setup_workspace(tmp_path)
    config = _cascade_config(ws)
    ev = PerTaskEvaluator({"t1": 0.3, "t2": 0.3, "t3": 0.9, "t4": 0.9})

    Orchestrator(ws, config, proposer=MockProposer(), evaluator=ev).run()

    # Base harness is scored in full (cascade never applies to it).
    assert ev.calls[0] == ["t1", "t2", "t3", "t4"]
    # Candidates run only stage 1 and are gated → stage 2 never runs alone.
    assert ["t1", "t2"] in ev.calls
    assert ["t3", "t4"] not in ev.calls


def test_cascade_runs_full_for_strong_candidate(tmp_path):
    """A candidate clearing stage 1 should proceed to the full task set."""
    ws = _setup_workspace(tmp_path)
    config = _cascade_config(ws)
    ev = PerTaskEvaluator({"t1": 0.8, "t2": 0.8, "t3": 0.8, "t4": 0.8})

    orch = Orchestrator(ws, config, proposer=MockProposer(), evaluator=ev)
    orch.run()

    assert ["t1", "t2"] in ev.calls  # stage 1
    assert ["t3", "t4"] in ev.calls  # stage 2 ran too
    cand = next(e for e in orch.search_log.entries if e.iteration == 1)
    assert set(cand.task_scores) == {"t1", "t2", "t3", "t4"}


def test_cascade_disabled_runs_full(tmp_path):
    """With cascade off, every evaluation uses the full task list."""
    ws = _setup_workspace(tmp_path)
    config = _cascade_config(ws, cascade=False)
    ev = PerTaskEvaluator({"t1": 0.3, "t2": 0.3, "t3": 0.9, "t4": 0.9})

    Orchestrator(ws, config, proposer=MockProposer(), evaluator=ev).run()

    assert ["t1", "t2"] not in ev.calls
    assert all(call == ["t1", "t2", "t3", "t4"] for call in ev.calls)


def test_cascade_base_always_full(tmp_path):
    """The base harness is fully evaluated even when candidates are gated."""
    ws = _setup_workspace(tmp_path)
    config = _cascade_config(ws, cascade_threshold=0.99)  # gate every candidate
    ev = PerTaskEvaluator({"t1": 0.5, "t2": 0.5, "t3": 0.5, "t4": 0.5})

    Orchestrator(ws, config, proposer=MockProposer(), evaluator=ev).run()

    assert ev.calls[0] == ["t1", "t2", "t3", "t4"]


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
