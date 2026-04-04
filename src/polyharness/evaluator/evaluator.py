"""Evaluator — runs candidate harness code and produces scores."""

from __future__ import annotations

import json
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvalResult:
    """Result of evaluating a candidate on all tasks."""

    overall_score: float
    task_scores: dict[str, float] = field(default_factory=dict)
    traces: dict[str, dict] = field(default_factory=dict)


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
            for task_path in tasks:
                task_name = Path(task_path).stem
                result = self._run_script(eval_script, candidate_dir, task_path)
                traces[task_name] = result
                task_scores[task_name] = result.get("score", 0.0)
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

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.cwd or candidate_dir),
            )
        except subprocess.TimeoutExpired:
            return {"score": 0.0, "error": "timeout", "stdout": "", "stderr": ""}

        result = {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exitcode": proc.returncode,
        }

        # Try to parse JSON from stdout
        try:
            output = json.loads(proc.stdout)
            result.update(output)
        except (json.JSONDecodeError, ValueError):
            # If stdout isn't JSON, try to extract a score from the last line
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
