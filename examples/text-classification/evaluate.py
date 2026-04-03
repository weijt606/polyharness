"""Evaluator for the text-classification example.

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


def evaluate(candidate_dir: Path, task_file: Path | None = None) -> dict:
    """Run evaluation and return scores."""
    harness = load_harness(candidate_dir)

    # Find test cases
    if task_file and task_file.exists():
        test_cases = json.loads(task_file.read_text())
    else:
        # Search for tasks in likely locations
        search_dirs = [
            candidate_dir.parent.parent,  # workspace root when inside candidates/iter_N/
            candidate_dir.parent,          # workspace root when inside base_harness/
            Path(__file__).parent,          # same directory as this script
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
    total = len(test_cases)
    task_scores = {}

    for i, case in enumerate(test_cases):
        text = case["text"]
        expected = case["label"]
        task_name = f"case_{i:03d}"

        try:
            prediction = harness.classify(text)
            is_correct = prediction == expected
            correct += int(is_correct)
            task_scores[task_name] = 1.0 if is_correct else 0.0
        except Exception as e:
            task_scores[task_name] = 0.0

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
    print(json.dumps(result))
