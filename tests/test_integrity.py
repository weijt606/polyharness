"""Tests for evaluation integrity: tamper detection and holdout isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polyharness.evaluator import BaseEvaluator, EvalResult
from polyharness.integrity import HoldoutVault, IntegrityError, IntegrityGuard
from polyharness.orchestrator import Orchestrator
from polyharness.proposer.base import BaseProposer
from polyharness.workspace import Workspace

# ---------------------------------------------------------------------------
# IntegrityGuard
# ---------------------------------------------------------------------------


def test_guard_passes_when_unchanged(tmp_path):
    (tmp_path / "evaluate.py").write_text("print(1)")
    guard = IntegrityGuard(tmp_path, ["evaluate.py"])
    assert guard.verify() == []
    guard.verify_or_raise()  # no exception


def test_guard_detects_modification(tmp_path):
    (tmp_path / "evaluate.py").write_text("print(1)")
    guard = IntegrityGuard(tmp_path, ["evaluate.py"])
    (tmp_path / "evaluate.py").write_text("print(999)  # hacked")
    assert guard.verify() == ["evaluate.py"]
    with pytest.raises(IntegrityError, match="evaluate.py"):
        guard.verify_or_raise()


def test_guard_detects_deletion_and_creation(tmp_path):
    (tmp_path / "t1.json").write_text("{}")
    guard = IntegrityGuard(tmp_path, ["t1.json", "t2.json"])  # t2 doesn't exist
    (tmp_path / "t1.json").unlink()
    (tmp_path / "t2.json").write_text("{}")  # appearing is also a change
    assert set(guard.verify()) == {"t1.json", "t2.json"}


# ---------------------------------------------------------------------------
# HoldoutVault
# ---------------------------------------------------------------------------


def test_vault_stash_hides_and_restore_returns(tmp_path):
    (tmp_path / "tasks").mkdir()
    test_file = tmp_path / "tasks" / "test_1.json"
    test_file.write_text('{"q": "secret"}')

    vault = HoldoutVault(tmp_path, ["tasks/test_1.json"])
    vault.stash()
    assert not test_file.exists()

    vault.restore()
    assert test_file.read_text() == '{"q": "secret"}'
    assert not (tmp_path / HoldoutVault.VAULT_DIR).exists()


def test_vault_recovers_after_crash(tmp_path):
    (tmp_path / "t.json").write_text("data")
    vault = HoldoutVault(tmp_path, ["t.json"])
    vault.stash()
    del vault  # crash: no restore

    # Next run stashes again — recovery must restore the old stash first
    vault2 = HoldoutVault(tmp_path, ["t.json"])
    vault2.stash()
    assert not (tmp_path / "t.json").exists()
    vault2.restore()
    assert (tmp_path / "t.json").read_text() == "data"


def test_vault_verify_detects_tampering(tmp_path):
    (tmp_path / "t.json").write_text("original")
    vault = HoldoutVault(tmp_path, ["t.json"])
    vault.stash()
    vault.restore()
    (tmp_path / "t.json").write_text("tampered")
    with pytest.raises(IntegrityError, match="t.json"):
        vault.verify_restored()


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------


class TamperingProposer(BaseProposer):
    """Simulates a reward-hacking agent that rewrites the evaluate script."""

    def propose(self, workspace_root, candidate_dir, iteration, parent):
        (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.5\n")
        (workspace_root / "evaluate.py").write_text(
            'import json; print(json.dumps({"overall_score": 1.0}))'
        )
        return {"changes_summary": "totally legitimate improvement"}


class HonestProposer(BaseProposer):
    def propose(self, workspace_root, candidate_dir, iteration, parent):
        (candidate_dir / "harness.py").write_text(
            f"SCORE_HINT = {0.3 + iteration * 0.1}\n"
        )
        return {"changes_summary": "ok"}


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
    (ws.root / "evaluate.py").write_text(
        'import json; print(json.dumps({"overall_score": 0.3}))'
    )
    return ws


def test_run_aborts_when_evaluate_script_tampered(tmp_path):
    ws = _ws(tmp_path)
    config = ws.load_config()
    config.search.max_iterations = 3
    config.search.early_stop_patience = 10

    orch = Orchestrator(
        ws, config, proposer=TamperingProposer(), evaluator=HintEvaluator()
    )
    with pytest.raises(IntegrityError, match="modified during the run"):
        orch.run()
    # The tampered iteration must not have been logged as a real candidate.
    assert all(e.iteration == 0 for e in orch.search_log.entries)


def test_holdout_tasks_hidden_during_search(tmp_path):
    """While the proposer runs, test task files must not be in the workspace."""
    ws = _ws(tmp_path)
    (ws.root / "val.json").write_text("{}")
    test_file = ws.root / "test.json"
    test_file.write_text('{"answer": 42}')

    seen: dict[str, bool] = {}

    class SpyProposer(BaseProposer):
        def propose(self, workspace_root, candidate_dir, iteration, parent):
            seen["test_visible"] = (workspace_root / "test.json").exists()
            (candidate_dir / "harness.py").write_text("SCORE_HINT = 0.6\n")
            return {"changes_summary": "spy"}

    config = ws.load_config()
    config.search.max_iterations = 1
    config.search.early_stop_patience = 5
    config.evaluator.eval_split = True
    config.evaluator.val_tasks = ["val.json"]
    config.evaluator.test_tasks = ["test.json"]

    class PerTaskEval(BaseEvaluator):
        def evaluate(self, candidate_dir, tasks):
            ts = {Path(t).stem: 0.6 for t in tasks}
            return EvalResult(
                overall_score=sum(ts.values()) / len(ts), task_scores=ts
            )

    result = Orchestrator(
        ws, config, proposer=SpyProposer(), evaluator=PerTaskEval()
    ).run()

    assert seen["test_visible"] is False, "test tasks leaked into the search"
    # Restored afterwards, and the holdout score was produced from them.
    assert test_file.read_text() == '{"answer": 42}'
    assert result.test_score is not None
    holdout = json.loads((ws.summary_dir / "holdout_test.json").read_text())
    assert holdout["iteration"] == result.best_iteration
