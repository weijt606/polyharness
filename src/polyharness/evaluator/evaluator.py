"""Evaluator — runs candidate harness code and produces scores."""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from polyharness.utils.proc import run_process_group


@dataclass
class EvalResult:
    """Result of evaluating a candidate on all tasks."""

    overall_score: float
    task_scores: dict[str, float] = field(default_factory=dict)
    traces: dict[str, dict] = field(default_factory=dict)
    gated: bool = False  # cascade stage-1 gate fired; stage-2 tasks not run


def _task_keys(tasks: list[str]) -> dict[str, str]:
    """Map each task path to a unique trace/score key.

    Uses the file stem when unambiguous; falls back to the full relative path
    (separators flattened) when two tasks share a stem — otherwise
    `easy/cases.json` and `hard/cases.json` would silently overwrite each
    other's scores and traces.
    """
    stems = [Path(t).stem for t in tasks]
    keys: dict[str, str] = {}
    for task, stem in zip(tasks, stems):
        if stems.count(stem) == 1:
            keys[task] = stem
        else:
            keys[task] = str(Path(task).with_suffix("")).replace("/", "__").replace("\\", "__")
    return keys


class BaseEvaluator(ABC):
    """Abstract evaluator interface."""

    @abstractmethod
    def evaluate(self, candidate_dir: Path, tasks: list[str]) -> EvalResult:
        """Evaluate a candidate harness against the given tasks."""
        ...


class PythonEvaluator(BaseEvaluator):
    """Evaluator that runs a Python evaluate script.

    The evaluate script is expected to:
    1. Accept the candidate directory as the first argument
    2. Print a JSON object to stdout with keys: overall_score, task_scores
    """

    def __init__(self, entry: str = "evaluate.py", timeout: int = 300, cwd: Path | None = None):
        self.entry = entry
        self.timeout = timeout
        self.cwd = cwd

    def evaluate(self, candidate_dir: Path, tasks: list[str]) -> EvalResult:
        eval_script = self._resolve_script(candidate_dir)

        if not eval_script.exists():
            raise FileNotFoundError(f"Evaluator script not found: {eval_script}")

        traces: dict[str, dict] = {}
        task_scores: dict[str, float] = {}

        if tasks:
            # Run per-task evaluation
            keys = _task_keys(tasks)
            for task_path in tasks:
                task_name = keys[task_path]
                result = self._run_script(eval_script, candidate_dir, task_path)
                traces[task_name] = result
                # Contract fallback: template evaluate scripts emit
                # `overall_score`; accept it when `score` is absent so
                # per-task mode doesn't silently record 0.0 for every task.
                raw = result.get("score", result.get("overall_score", 0.0))
                try:
                    task_scores[task_name] = float(raw)
                except (TypeError, ValueError):
                    task_scores[task_name] = 0.0
                self._write_traces(candidate_dir, task_name, result)

            overall = sum(task_scores.values()) / len(task_scores) if task_scores else 0.0
        else:
            # Run script once with no specific task — script does its own evaluation
            result = self._run_script(eval_script, candidate_dir, None)
            traces["default"] = result
            task_scores = result.get("task_scores", {})
            overall = result.get("overall_score", result.get("score", 0.0))
            self._write_traces(candidate_dir, "default", result)

        return EvalResult(
            overall_score=overall,
            task_scores=task_scores,
            traces=traces,
        )

    def _resolve_script(self, candidate_dir: Path) -> Path:
        # Look in workspace root (cwd) first, then candidate dir
        if self.cwd:
            script = self.cwd / self.entry
            if script.exists():
                return script
        return candidate_dir / self.entry

    def _run_script(
        self, script: Path, candidate_dir: Path, task_path: str | None
    ) -> dict:
        cmd = [sys.executable, str(script), str(candidate_dir)]
        if task_path:
            cmd.append(task_path)

        # Process-group run: evaluate scripts spawn agent CLIs / LLM calls;
        # on timeout those grandchildren must die too, and partial output is
        # kept so the timeout can be diagnosed from traces.
        proc = run_process_group(
            cmd,
            timeout=self.timeout,
            cwd=str(self.cwd or candidate_dir),
        )
        if proc.timed_out:
            return {
                "score": 0.0,
                "error": "timeout",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }

        result = {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exitcode": proc.returncode,
        }

        # Try to parse JSON from stdout
        parsed: object = None
        try:
            parsed = json.loads(proc.stdout)
        except (json.JSONDecodeError, ValueError):
            parsed = None

        if isinstance(parsed, dict):
            result.update(parsed)
        elif isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            # A bare JSON number (e.g. a script that prints just `0.65`)
            # used to crash result.update(); treat it as the score.
            result["score"] = float(parsed)
        else:
            # Not JSON (or an unusable JSON type): extract a score from the
            # last stdout line.
            lines = proc.stdout.strip().splitlines()
            if lines:
                try:
                    result["score"] = float(lines[-1])
                except ValueError:
                    result["score"] = 0.0
            else:
                result["score"] = 0.0

        return result

    def _write_traces(self, candidate_dir: Path, task_name: str, result: dict) -> None:
        traces_dir = candidate_dir / "traces"
        traces_dir.mkdir(exist_ok=True)

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exitcode = result.get("exitcode", -1)

        (traces_dir / f"{task_name}.stdout").write_text(stdout)
        (traces_dir / f"{task_name}.stderr").write_text(stderr)
        (traces_dir / f"{task_name}.exitcode").write_text(str(exitcode) + "\n")

        metrics = {k: v for k, v in result.items() if k not in ("stdout", "stderr", "exitcode")}
        if metrics:
            (traces_dir / f"{task_name}.metrics.json").write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"
            )


def create_evaluator(config, cwd: Path | None = None) -> BaseEvaluator:
    """Factory: create an evaluator from config."""
    if config.type == "python":
        return PythonEvaluator(
            entry=config.entry,
            timeout=config.timeout,
            cwd=cwd,
        )
    raise ValueError(f"Unsupported evaluator type: {config.type}")
