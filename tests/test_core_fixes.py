"""Regression tests for core-loop correctness fixes (v0.3.0).

Covers: lineage recording, candidate-dir hygiene, base-harness traces,
cascade gating semantics, evaluator output contract, search-log resilience,
and the workspace run lock.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from polyharness.evaluator import BaseEvaluator, EvalResult
from polyharness.evaluator.evaluator import PythonEvaluator
from polyharness.orchestrator import Orchestrator
from polyharness.proposer.base import BaseProposer
from polyharness.search_log import SearchLog
from polyharness.workspace import Workspace


class HintProposer(BaseProposer):
    def __init__(self, hints=None):
        self.hints = hints or {}

    def propose(self, workspace_root, candidate_dir, iteration, parent):
        hint = self.hints.get(iteration, 0.3 + iteration * 0.1)
        (candidate_dir / "harness.py").write_text(f"SCORE_HINT = {hint}\n")
        return {"changes_summary": f"iter {iteration}"}


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
# Lineage
# ---------------------------------------------------------------------------


def test_search_log_records_actual_parent(tmp_path):
    """The log must record the parent the candidate was branched from, not
    best_iteration (they differ under tournament/pareto selection)."""
    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 5
    config.search.early_stop_patience = 20
    config.search.parent_selection = "tournament"
    config.search.seed = 7

    orch = Orchestrator(ws, config, proposer=HintProposer(), evaluator=HintEvaluator())
    orch.run()

    for e in orch.search_log.entries:
        if e.iteration == 0:
            continue
        meta = json.loads(
            (ws.candidate_path(e.iteration) / "metadata.json").read_text()
        )
        meta_parent = meta["parent"]  # "iter_N"
        assert meta_parent == f"iter_{e.parent}", (
            f"iter_{e.iteration}: log parent {e.parent} != metadata {meta_parent}"
        )


# ---------------------------------------------------------------------------
# Candidate dir hygiene
# ---------------------------------------------------------------------------


def test_prepare_candidate_strips_parent_artifacts(tmp_path):
    ws = _ws(tmp_path)
    parent_dir = ws.prepare_candidate(1, parent=None)
    (parent_dir / "score.json").write_text('{"overall_score": 0.9}')
    (parent_dir / "metadata.json").write_text("{}")
    (parent_dir / "traces").mkdir(exist_ok=True)
    (parent_dir / "traces" / "t.stdout").write_text("old trace")

    child = ws.prepare_candidate(2, parent=1)

    assert not (child / "score.json").exists()
    assert not (child / "metadata.json").exists()
    assert not (child / "traces" / "t.stdout").exists()
    assert (child / "harness.py").exists()


def test_failed_iteration_leaves_no_candidate_dir(tmp_path):
    """A proposer crash must not leave a half-built candidate directory."""

    class ExplodingProposer(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            raise RuntimeError("boom")

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 2
    config.search.early_stop_patience = 1

    orch = Orchestrator(ws, config, proposer=ExplodingProposer(), evaluator=HintEvaluator())
    orch.run()

    assert not ws.candidate_path(1).exists()
    lb = json.loads((ws.summary_dir / "leaderboard.json").read_text())
    iters = [e["iteration"] for e in lb]
    assert iters.count(0) == 1  # no duplicate entries from stale copies


def test_base_traces_stored_in_iter0_not_base_harness(tmp_path):
    """Base evaluation traces belong in candidates/iter_0/, and base_harness/
    must stay pristine."""
    ws = _ws(tmp_path)
    eval_script = ws.root / "evaluate.py"
    eval_script.write_text(
        textwrap.dedent("""\
            import json
            print(json.dumps({"overall_score": 0.5, "task_scores": {"t": 0.5}}))
        """)
    )
    config = ws.load_config()
    config.search.max_iterations = 1
    config.search.early_stop_patience = 5

    orch = Orchestrator(ws, config, proposer=HintProposer())
    orch.run()

    iter0_traces = list((ws.candidate_path(0) / "traces").iterdir())
    assert iter0_traces, "iter_0 must contain the base evaluation traces"
    assert not (ws.base_harness_dir / "traces").exists()
    assert not (ws.base_harness_dir / "score.json").exists()


# ---------------------------------------------------------------------------
# Cascade gating
# ---------------------------------------------------------------------------


def test_gated_candidate_cannot_beat_fully_evaluated_best(tmp_path):
    """A stage-1-only score must be penalized over the full denominator so a
    never-fully-evaluated candidate can't become best."""

    class SplitEvaluator(BaseEvaluator):
        def evaluate(self, candidate_dir, tasks):
            # Base (full list) scores poorly; candidates ace stage 1 only.
            names = [Path(t).stem for t in tasks]
            if len(tasks) == 4:  # full evaluation (base harness)
                ts = {n: 0.35 for n in names}
            else:  # stage-1 subset
                ts = {n: 0.39 for n in names}
            return EvalResult(
                overall_score=sum(ts.values()) / len(ts), task_scores=ts
            )

    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 1
    config.search.early_stop_patience = 5
    config.evaluator.tasks = ["t1.json", "t2.json", "t3.json", "t4.json"]
    config.evaluator.cascade = True
    config.evaluator.cascade_stage1 = 2
    config.evaluator.cascade_threshold = 0.4  # gates the 0.39 candidate

    orch = Orchestrator(ws, config, proposer=HintProposer(), evaluator=SplitEvaluator())
    result = orch.run()

    assert result.best_iteration == 0, "gated partial score must not win"
    meta = json.loads((ws.candidate_path(1) / "metadata.json").read_text())
    assert meta.get("cascade_gated") is True
    entry = next(e for e in orch.search_log.entries if e.iteration == 1)
    assert entry.score == pytest.approx(0.39 * 2 / 4)


# ---------------------------------------------------------------------------
# Evaluator output contract
# ---------------------------------------------------------------------------


def _write_eval(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "evaluate.py"
    script.write_text(textwrap.dedent(body))
    return script


def test_evaluator_bare_json_number(tmp_path):
    """A script whose entire stdout is `0.65` must score 0.65, not crash."""
    _write_eval(tmp_path, "print(0.65)\n")
    cand = tmp_path / "cand"
    cand.mkdir()
    ev = PythonEvaluator(cwd=tmp_path)
    result = ev.evaluate(candidate_dir=cand, tasks=[])
    assert result.overall_score == pytest.approx(0.65)


def test_evaluator_json_list_scores_zero_not_crash(tmp_path):
    _write_eval(tmp_path, "print('[0.1, 0.2]')\n")
    cand = tmp_path / "cand"
    cand.mkdir()
    ev = PythonEvaluator(cwd=tmp_path)
    result = ev.evaluate(candidate_dir=cand, tasks=[])
    assert result.overall_score == 0.0


def test_evaluator_per_task_accepts_overall_score_key(tmp_path):
    """Template scripts emit overall_score; per-task mode must accept it."""
    _write_eval(
        tmp_path,
        """\
        import json
        print(json.dumps({"overall_score": 0.8}))
        """,
    )
    (tmp_path / "t1.json").write_text("{}")
    cand = tmp_path / "cand"
    cand.mkdir()
    ev = PythonEvaluator(cwd=tmp_path)
    result = ev.evaluate(candidate_dir=cand, tasks=["t1.json"])
    assert result.task_scores["t1"] == pytest.approx(0.8)


def test_evaluator_duplicate_task_stems_kept_distinct(tmp_path):
    """easy/cases.json and hard/cases.json must not overwrite each other."""
    _write_eval(
        tmp_path,
        """\
        import json, sys
        score = 0.9 if "easy" in sys.argv[2] else 0.1
        print(json.dumps({"score": score}))
        """,
    )
    for sub in ("easy", "hard"):
        d = tmp_path / sub
        d.mkdir()
        (d / "cases.json").write_text("{}")
    cand = tmp_path / "cand"
    cand.mkdir()
    ev = PythonEvaluator(cwd=tmp_path)
    result = ev.evaluate(candidate_dir=cand, tasks=["easy/cases.json", "hard/cases.json"])
    assert len(result.task_scores) == 2
    assert result.overall_score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Search log resilience
# ---------------------------------------------------------------------------


def test_search_log_skips_corrupt_lines(tmp_path):
    log_path = tmp_path / "search_log.jsonl"
    log = SearchLog(log_path)
    log.append(iteration=0, parent=None, score=0.3)
    log.append(iteration=1, parent=0, score=0.5)
    # Simulate a truncated write (process killed mid-append)
    with open(log_path, "a") as f:
        f.write('{"iteration": 2, "par')

    with pytest.warns(UserWarning, match="corrupt search log line"):
        reloaded = SearchLog(log_path)
    assert len(reloaded) == 2
    assert reloaded.best_score == 0.5


def test_search_log_ignores_unknown_fields(tmp_path):
    """Logs written by newer versions (extra fields) must still load."""
    log_path = tmp_path / "search_log.jsonl"
    entry = {
        "iteration": 0,
        "parent": None,
        "score": 0.4,
        "best_so_far": 0.4,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "task_scores": {},
        "future_field": "whatever",
    }
    log_path.write_text(json.dumps(entry) + "\n")
    reloaded = SearchLog(log_path)
    assert len(reloaded) == 1
    assert reloaded.best_score == 0.4


# ---------------------------------------------------------------------------
# Workspace lock
# ---------------------------------------------------------------------------


def test_workspace_lock_blocks_second_run(tmp_path):
    ws = _ws(tmp_path)
    with ws.exclusive_lock():
        ws2 = Workspace(ws.root)
        with pytest.raises(RuntimeError, match="already active"):
            with ws2.exclusive_lock():
                pass
    # Released after exit — can lock again
    with ws.exclusive_lock():
        pass
