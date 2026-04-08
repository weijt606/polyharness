"""Tests for the example tasks."""

import json
import sys
from pathlib import Path

# Template directories (bundled inside the package)
TEMPLATE_BASE = Path(__file__).parent.parent / "src" / "polyharness" / "templates"
EXAMPLE_DIR = TEMPLATE_BASE / "text-classification"
MATH_EXAMPLE_DIR = TEMPLATE_BASE / "math-word-problems"


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
        question = "A store sells apples for $2 each. If Mary buys 5 apples, how much does she pay?"
        assert math_harness.solve(question) == 10.0
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


# --- Code generation example ---

CODEGEN_EXAMPLE_DIR = TEMPLATE_BASE / "code-generation"


def test_codegen_base_harness_generate():
    """Test that the code-gen base harness can generate code."""
    sys.path.insert(0, str(CODEGEN_EXAMPLE_DIR / "base_harness"))
    try:
        import harness as cg_harness
        code = cg_harness.generate("Return the sum of numbers in a list")
        assert isinstance(code, str)
        assert "sum" in code
    finally:
        sys.path.pop(0)
        if "harness" in sys.modules:
            del sys.modules["harness"]
        if "cg_harness" in sys.modules:
            del sys.modules["cg_harness"]


def test_codegen_evaluate_script():
    """Test that the code-gen evaluator runs and scores the base harness."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(CODEGEN_EXAMPLE_DIR / "evaluate.py"),
         str(CODEGEN_EXAMPLE_DIR / "base_harness")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "overall_score" in output
    assert output["total"] == 60  # 20 tasks × 3 inputs each
    assert 0.0 < output["overall_score"] < 1.0


# --- API-calling example ---

API_EXAMPLE_DIR = TEMPLATE_BASE / "api-calling"


def test_api_base_harness_route():
    """Test that the API base harness can route queries."""
    sys.path.insert(0, str(API_EXAMPLE_DIR / "base_harness"))
    try:
        import harness as api_harness
        result = api_harness.route("What is the weather in London?")
        assert isinstance(result, dict)
        assert "endpoint" in result
        assert "params" in result
        assert result["endpoint"] == "get_weather"
    finally:
        sys.path.pop(0)
        if "harness" in sys.modules:
            del sys.modules["harness"]
        if "api_harness" in sys.modules:
            del sys.modules["api_harness"]


def test_api_evaluate_script():
    """Test that the API evaluator runs and scores the base harness."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(API_EXAMPLE_DIR / "evaluate.py"),
         str(API_EXAMPLE_DIR / "base_harness")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "overall_score" in output
    assert output["total"] == 20
    assert 0.0 < output["overall_score"] < 1.0


# --- RAG-QA example ---

RAG_EXAMPLE_DIR = TEMPLATE_BASE / "rag-qa"


def test_rag_base_harness_retrieve():
    """Test that the RAG base harness can retrieve and answer."""
    sys.path.insert(0, str(RAG_EXAMPLE_DIR / "base_harness"))
    try:
        import harness as rag_harness
        rag_harness.set_knowledge_base([
            {"id": "doc1", "title": "Python", "content": "Python is a programming language."},
        ])
        result = rag_harness.retrieve_and_answer("What is Python?")
        assert isinstance(result, dict)
        assert "answer" in result
        assert "source_id" in result
    finally:
        sys.path.pop(0)
        if "harness" in sys.modules:
            del sys.modules["harness"]
        if "rag_harness" in sys.modules:
            del sys.modules["rag_harness"]


def test_rag_evaluate_script():
    """Test that the RAG evaluator runs and scores the base harness."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(RAG_EXAMPLE_DIR / "evaluate.py"),
         str(RAG_EXAMPLE_DIR / "base_harness")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "overall_score" in output
    assert output["total"] == 20
    assert 0.0 < output["overall_score"] < 1.0
