"""Evaluator for the api-calling example.

Usage: python evaluate.py <candidate_dir> [task_file]

Loads the harness from the candidate directory, runs it against test cases,
and outputs a JSON score to stdout.

Scoring:
  - Endpoint correct: 0.5 points
  - Each expected param correct: remaining 0.5 / num_params
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


def _score_case(result: dict, expected_endpoint: str, expected_params: dict) -> float:
    """Score a single API routing result (0.0 to 1.0)."""
    score = 0.0

    # Endpoint match: 0.5 points
    if result.get("endpoint") == expected_endpoint:
        score += 0.5

    # Param matches: 0.5 points divided among expected params
    if expected_params:
        param_weight = 0.5 / len(expected_params)
        result_params = result.get("params", {})
        for key, expected_val in expected_params.items():
            actual_val = result_params.get(key, "")
            # Normalize for comparison: lowercase string matching
            if str(actual_val).lower().strip() == str(expected_val).lower().strip():
                score += param_weight
    else:
        # No params expected — full score if endpoint is right
        if result.get("endpoint") == expected_endpoint:
            score += 0.5

    return score


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

    total_score = 0.0
    total = len(test_cases)
    task_scores = {}

    for i, case in enumerate(test_cases):
        query = case["query"]
        expected_endpoint = case["expected_endpoint"]
        expected_params = case["expected_params"]
        task_name = f"case_{i:03d}"

        try:
            result = harness.route(query)
            case_score = _score_case(result, expected_endpoint, expected_params)
            task_scores[task_name] = case_score
            total_score += case_score
        except Exception:
            task_scores[task_name] = 0.0

    overall = total_score / total if total > 0 else 0.0

    return {
        "overall_score": overall,
        "task_scores": task_scores,
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
