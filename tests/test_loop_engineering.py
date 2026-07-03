"""Tests for the loop-engineering upgrades (v0.3.0).

Reflective retry feedback, the LessonBook evolution memory, bandit
persistence + delta rewards, failure/patience separation, and parallel
task evaluation.
"""

from __future__ import annotations

import textwrap

import pytest

from polyharness.evaluator import BaseEvaluator, EvalResult
from polyharness.evaluator.evaluator import PythonEvaluator
from polyharness.lessons import LessonBook
from polyharness.orchestrator import Orchestrator
from polyharness.proposer.bandit import BackendBandit
from polyharness.proposer.base import FEEDBACK_FILENAME, BaseProposer
from polyharness.workspace import Workspace


class HintEvaluator(BaseEvaluator):
    def evaluate(self, candidate_dir, tasks):
        score = 0.3
        harness = candidate_dir / "harness.py"
        if harness.exists():
            for line in harness.read_text().splitlines():
                if line.startswith("SCORE_HINT"):
                    score = float(line.split("=")[1].strip())
        score = min(score, 1.0)
        return EvalResult(overall_score=score, task_scores={"t": score})


def _ws(tmp_path) -> Workspace:
    ws = Workspace.init(tmp_path / "ws")
    (ws.base_harness_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
    return ws


# ---------------------------------------------------------------------------
# Reflective retry feedback
# ---------------------------------------------------------------------------


def test_novelty_retry_receives_feedback_file(tmp_path):
    """The regeneration attempt must find PROPOSER_FEEDBACK.md explaining the
    rejection, and produce something different because of it."""
    feedback_seen: list[str] = []

    class LearnsFromFeedback(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            fb = candidate_dir / FEEDBACK_FILENAME
            if fb.exists():
                feedback_seen.append(fb.read_text())
                (candidate_dir / "harness.py").write_text(
                    "import statistics\nSCORE_HINT = 0.55\n"
                    "def totally_new_mechanism(xs):\n"
                    "    return statistics.median(xs)\n"
                )
            else:
                # First attempt: identical to base → near-duplicate
                (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
            return {"changes_summary": "attempt"}

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 1
    config.search.early_stop_patience = 5
    config.search.novelty_filter = True
    config.search.novelty_max_retries = 1

    orch = Orchestrator(
        ws, config, proposer=LearnsFromFeedback(), evaluator=HintEvaluator()
    )
    result = orch.run()

    assert feedback_seen, "retry must receive the feedback file"
    assert "iter_0" in feedback_seen[0]  # names the duplicated candidate
    assert result.best_iteration == 1  # the informed retry was accepted
    # Feedback file is transient — not part of the stored candidate.
    assert not (ws.candidate_path(1) / FEEDBACK_FILENAME).exists()


def test_failure_feedback_reaches_next_iteration(tmp_path):
    feedback_seen: list[str] = []

    class FailsOnceThenReads(BaseProposer):
        def __init__(self):
            self.calls = 0

        def propose(self, workspace_root, candidate_dir, iteration, parent):
            self.calls += 1
            fb = candidate_dir / FEEDBACK_FILENAME
            if fb.exists():
                feedback_seen.append(fb.read_text())
            if self.calls == 1:
                raise RuntimeError("transient network explosion")
            (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.6\n")
            return {"changes_summary": "recovered"}

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 5

    Orchestrator(
        ws, config, proposer=FailsOnceThenReads(), evaluator=HintEvaluator()
    ).run()

    assert feedback_seen and "network explosion" in feedback_seen[0]


# ---------------------------------------------------------------------------
# LessonBook
# ---------------------------------------------------------------------------


def test_lessons_recorded_and_rendered(tmp_path):
    class UpDownProposer(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            hint = {1: 0.6, 2: 0.4, 3: 0.8}.get(iteration, 0.3)
            (candidate_dir / "harness.py").write_text(f"SCORE_HINT = {hint}\n")
            return {"changes_summary": f"tweak {iteration}: adjusted strategy"}

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 3
    config.search.early_stop_patience = 10

    orch = Orchestrator(
        ws, config, proposer=UpDownProposer(), evaluator=HintEvaluator()
    )
    orch.run()

    lessons = orch.lessons.load()
    verdicts = {ls["iteration"]: ls["verdict"] for ls in lessons}
    assert verdicts[1] == "improved"
    assert verdicts[2] == "regressed"
    assert verdicts[3] == "improved"

    md = (ws.summary_dir / "LESSONS.md").read_text()
    assert "What improved the score" in md
    assert "What regressed or failed" in md
    assert "tweak 3" in md


def test_lessonbook_tolerates_truncated_tail(tmp_path):
    book = LessonBook(tmp_path)
    book.record(iteration=1, parent=0, verdict="improved", score=0.5, parent_score=0.3)
    with open(book.jsonl_path, "a") as f:
        f.write('{"iteration": 2, "verd')
    assert len(book.load()) == 1


# ---------------------------------------------------------------------------
# Bandit: delta rewards + persistence
# ---------------------------------------------------------------------------


def test_bandit_reward_function(tmp_path):
    ws = Workspace.init(tmp_path / "ws2")
    (ws.base_harness_dir / "harness.py").write_text("SCORE_HINT = 0.3\n")
    orch = Orchestrator(ws, ws.load_config(), proposer=object(), evaluator=HintEvaluator())  # type: ignore[arg-type]

    assert orch._bandit_reward(0.3, 0.5) == 0.0  # regression → 0
    assert orch._bandit_reward(0.5, 0.3) == 1.0  # first improvement → 1
    assert orch._bandit_reward(0.4, 0.3) == pytest.approx(0.5)  # half the max delta
    assert orch._bandit_reward(0.9, 0.3) == 1.0  # new max delta


def test_bandit_update_rejects_out_of_range():
    b = BackendBandit(["a", "b"])
    with pytest.raises(ValueError):
        b.update("a", 1.5)


def test_bandit_state_roundtrip():
    b = BackendBandit(["a", "b"])
    b.update("a", 1.0)
    b.update("a", 0.25)
    b.update("b", 0.0)
    state = b.to_dict()

    b2 = BackendBandit(["a", "b", "c"])  # 'c' is newly configured
    b2.load_dict(state)
    assert b2.stats()["a"]["pulls"] == 2
    assert b2.stats()["a"]["mean_reward"] == pytest.approx(0.625)
    assert b2.stats()["c"]["pulls"] == 0  # cold start preserved


def test_bandit_resumes_from_saved_state(tmp_path):
    class ImprovingProposer(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            (candidate_dir / "harness.py").write_text(
                f"SCORE_HINT = {min(0.4 + iteration * 0.1, 1.0)}\n"
            )
            return {"changes_summary": "up"}

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 20
    config.proposer.ensemble = ["local", "api"]

    proposers = {"local": ImprovingProposer(), "api": ImprovingProposer()}
    orch1 = Orchestrator(ws, config, proposers=proposers, evaluator=HintEvaluator())
    orch1.run()
    pulls_before = sum(s["pulls"] for s in orch1.bandit.stats().values())
    assert pulls_before > 0

    config2 = config.model_copy(deep=True)
    config2.search.max_iterations = 4
    orch2 = Orchestrator(ws, config2, proposers=proposers, evaluator=HintEvaluator())
    orch2.run(resume=True)
    pulls_after = sum(s["pulls"] for s in orch2.bandit.stats().values())
    # Resume restored the earlier pulls instead of cold-starting from zero.
    assert pulls_after > pulls_before


# ---------------------------------------------------------------------------
# Failure counter separated from patience
# ---------------------------------------------------------------------------


def test_failures_do_not_consume_patience(tmp_path):
    """Alternating failure/success must never trip early-stop patience, and
    failures are recorded as events."""

    class Alternating(BaseProposer):
        def __init__(self):
            self.calls = 0

        def propose(self, workspace_root, candidate_dir, iteration, parent):
            self.calls += 1
            if self.calls % 2 == 1:
                raise RuntimeError("flaky infra")
            (candidate_dir / "harness.py").write_text(
                f"SCORE_HINT = {min(0.3 + 0.05 * iteration, 1.0)}\n"
            )
            return {"changes_summary": "ok"}

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 8
    config.search.early_stop_patience = 2  # tight: failures would trip it
    config.search.max_consecutive_failures = 3

    orch = Orchestrator(ws, config, proposer=Alternating(), evaluator=HintEvaluator())
    result = orch.run()

    failed = [e for e in orch.search_log.entries if e.status == "failed"]
    assert failed, "failures must be logged as events"
    # Successes kept improving, so the run used the full budget.
    assert result.total_iterations >= 7
    assert result.best_score > 0.3


def test_consecutive_failures_stop_run(tmp_path):
    class AlwaysFails(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            raise RuntimeError("backend down")

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 20
    config.search.early_stop_patience = 50
    config.search.max_consecutive_failures = 3

    orch = Orchestrator(ws, config, proposer=AlwaysFails(), evaluator=HintEvaluator())
    orch.run()

    failed = [e for e in orch.search_log.entries if e.status == "failed"]
    assert len(failed) == 3  # stopped at the failure cap, not at max_iterations


# ---------------------------------------------------------------------------
# Parallel evaluation
# ---------------------------------------------------------------------------


def test_parallel_evaluation_matches_serial(tmp_path):
    script = tmp_path / "evaluate.py"
    script.write_text(
        textwrap.dedent("""\
            import json, sys
            task = sys.argv[2]
            score = {"t1.json": 0.2, "t2.json": 0.4, "t3.json": 0.9}[task.split("/")[-1]]
            print(json.dumps({"score": score}))
        """)
    )
    for name in ("t1.json", "t2.json", "t3.json"):
        (tmp_path / name).write_text("{}")
    cand = tmp_path / "cand"
    cand.mkdir()
    tasks = ["t1.json", "t2.json", "t3.json"]

    serial = PythonEvaluator(cwd=tmp_path, parallel_tasks=1).evaluate(cand, tasks)
    parallel = PythonEvaluator(cwd=tmp_path, parallel_tasks=3).evaluate(cand, tasks)

    assert parallel.task_scores == serial.task_scores
    assert parallel.overall_score == pytest.approx(serial.overall_score)
    # Traces written for every task in both modes.
    assert (cand / "traces" / "t3.metrics.json").exists()
