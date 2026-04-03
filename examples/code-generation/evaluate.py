"""Evaluator for the code-generation example.

Usage: python evaluate.py <candidate_dir> [task_file]

Loads the harness from the candidate directory, runs it against test cases,
and outputs a JSON score to stdout.
"""

import importlib.util
import json
import sys
from pathlib import Path


def load_harness(candidate_dir: Path):
    """Dynamically load harness.py from a candidate directory."""
    harness_path = candidate_dir / "harness.py"
    if not harness_path.exists():
        raise FileNotFoundError(f"No harness.py in {candidate_dir}")

    spec = importlib.util.spec_from_file_location("harness", harness_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module spec from {harness_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exec_generated(code_body: str, args):
    """Execute a generated function body with the given args.

    The code body should use ``args`` as the input variable and
    ``return`` to produce the result.
    """
    namespace: dict = {}
    wrapped = f"def _generated(args):\n"
    for line in code_body.splitlines():
        wrapped += f"    {line}\n"
    exec(wrapped, namespace)  # noqa: S102 — sandboxed eval of generated code
    return namespace["_generated"](args)


def evaluate(candidate_dir: Path, task_file: Path | None = None) -> dict:
    """Run evaluation and return scores."""
    harness = load_harness(candidate_dir)

    # Find test cases
    if task_file and task_file.exists():
        test_cases = json.loads(task_file.read_text())
    else:
        search_dirs = [
            candidate_dir.parent.parent,
            candidate_dir.parent,
            Path(__file__).parent,
        ]
        test_cases = None
        for d in search_dirs:
            default_tasks = d / "tasks" / "test_cases.json"
            if default_tasks.exists():
                test_cases = json.loads(default_tasks.read_text())
                break
        if test_cases is None:
            return {"overall_score": 0.0, "error": "No test cases found"}

    correct = 0
    total = 0
    task_scores = {}

    for i, case in enumerate(test_cases):
        description = case["description"]
        test_inputs = case["test_inputs"]
        expected_outputs = case["expected_outputs"]
        task_name = f"case_{i:03d}"

        sub_correct = 0
        sub_total = len(test_inputs)

        for inp, exp in zip(test_inputs, expected_outputs):
            try:
                code_body = harness.generate(description)
                result = _exec_generated(code_body, inp)
                # Normalize comparison: convert to JSON-comparable form
                if result == exp:
                    sub_correct += 1
                elif json.dumps(result, sort_keys=True) == json.dumps(exp, sort_keys=True):
                    sub_correct += 1
            except Exception:
                pass

        task_score = sub_correct / sub_total if sub_total > 0 else 0.0
        task_scores[task_name] = task_score
        correct += sub_correct
        total += sub_total

    overall = correct / total if total > 0 else 0.0

    return {
        "overall_score": overall,
        "task_scores": task_scores,
        "correct": correct,
        "total": total,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evaluate.py <candidate_dir> [task_file]", file=sys.stderr)
        sys.exit(1)

    candidate_dir = Path(sys.argv[1])
    task_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    result = evaluate(candidate_dir, task_file)
    print(json.dumps(result, indent=2))
