"""Tests for the example tasks."""

import json
import sys
from pathlib import Path

# Example directories
EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "text-classification"
MATH_EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "math-word-problems"


def test_base_harness_classify():
    """Test that the base harness can classify text."""
    sys.path.insert(0, str(EXAMPLE_DIR / "base_harness"))
    try:
        import harness
        assert harness.classify("I love this!") == "positive"
        assert harness.classify("This is terrible.") == "negative"
        assert harness.classify("The meeting is at 3pm.") == "neutral"
    finally:
        sys.path.pop(0)
        if "harness" in sys.modules:
            del sys.modules["harness"]


def test_evaluate_script():
    """Test that the evaluator script runs and scores the base harness."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(EXAMPLE_DIR / "evaluate.py"), str(EXAMPLE_DIR / "base_harness")],
        capture_output=True,
        text=True,
        cwd=str(EXAMPLE_DIR),
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "overall_score" in output
    assert "task_scores" in output
    # Base harness should get > 0 but < 1.0 (it's naive)
    assert 0.0 < output["overall_score"] <= 1.0


# --- Math word problems example ---

def test_math_base_harness_solve():
    """Test that the math base harness can solve simple problems."""
    sys.path.insert(0, str(MATH_EXAMPLE_DIR / "base_harness"))
    try:
        import harness as math_harness
        # Product of first two numbers: 2 * 5 = 10 (correct for this case)
        assert math_harness.solve("A store sells apples for $2 each. If Mary buys 5 apples, how much does she pay?") == 10.0
        # Returns a float
        assert isinstance(math_harness.solve("What is 42?"), float)
    finally:
        sys.path.pop(0)
        if "harness" in sys.modules:
            del sys.modules["harness"]
        if "math_harness" in sys.modules:
            del sys.modules["math_harness"]


def test_math_evaluate_script():
    """Test that the math evaluator runs and scores the base harness."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(MATH_EXAMPLE_DIR / "evaluate.py"), str(MATH_EXAMPLE_DIR / "base_harness")],
        capture_output=True,
        text=True,
        cwd=str(MATH_EXAMPLE_DIR),
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "overall_score" in output
    assert "task_scores" in output
    assert output["total"] == 20
    # Naive harness should get some right but not all
    assert 0.0 < output["overall_score"] < 1.0
