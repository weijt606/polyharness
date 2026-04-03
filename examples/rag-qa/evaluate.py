"""Evaluator for the rag-qa example.

Usage: python evaluate.py <candidate_dir> [task_file]

Loads the harness from the candidate directory, runs it against test cases,
and outputs a JSON score to stdout.

Scoring per case:
  - Correct source document retrieved: 0.4 points
  - Expected answer substring found in harness answer: 0.6 points
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
        data = json.loads(task_file.read_text())
    else:
        search_dirs = [
            candidate_dir.parent.parent,
            candidate_dir.parent,
            Path(__file__).parent,
        ]
        data = None
        for d in search_dirs:
            default_tasks = d / "tasks" / "test_cases.json"
            if default_tasks.exists():
                data = json.loads(default_tasks.read_text())
                break
        if data is None:
            return {"overall_score": 0.0, "error": "No test cases found"}

    knowledge_base = data["knowledge_base"]
    test_cases = data["test_cases"]

    # Set knowledge base in harness
    if hasattr(harness, "set_knowledge_base"):
        harness.set_knowledge_base(knowledge_base)

    total_score = 0.0
    total = len(test_cases)
    task_scores = {}

    for i, case in enumerate(test_cases):
        question = case["question"]
        expected_answer = case["expected_answer"].lower()
        expected_source = case["expected_source"]
        task_name = f"case_{i:03d}"

        try:
            result = harness.retrieve_and_answer(question)
            case_score = 0.0

            # Source retrieval score (0.4)
            if result.get("source_id") == expected_source:
                case_score += 0.4

            # Answer extraction score (0.6)
            answer = result.get("answer", "").lower()
            if expected_answer in answer:
                case_score += 0.6

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
