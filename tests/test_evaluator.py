"""Tests for the Evaluator."""

import textwrap

from polyharness.evaluator import EvalResult, PythonEvaluator


def test_python_evaluator_json_output(tmp_path):
    """Test evaluator running a script that outputs JSON."""
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()

    # Create a simple evaluate script that returns JSON
    eval_script = tmp_path / "evaluate.py"
    eval_script.write_text(textwrap.dedent("""\
        import json, sys
        candidate_dir = sys.argv[1]
        result = {"overall_score": 0.75, "task_scores": {"t1": 0.8, "t2": 0.7}}
        print(json.dumps(result))
    """))

    evaluator = PythonEvaluator(entry="evaluate.py", timeout=30, cwd=tmp_path)
    result = evaluator.evaluate(candidate_dir, tasks=[])
    assert isinstance(result, EvalResult)
    assert result.overall_score == 0.75
    assert result.task_scores == {"t1": 0.8, "t2": 0.7}


def test_python_evaluator_plain_score(tmp_path):
    """Test evaluator running a script that outputs a plain float."""
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()

    eval_script = tmp_path / "evaluate.py"
    eval_script.write_text(textwrap.dedent("""\
        import sys
        print("Running evaluation...")
        print(0.65)
    """))

    evaluator = PythonEvaluator(entry="evaluate.py", timeout=30, cwd=tmp_path)
    result = evaluator.evaluate(candidate_dir, tasks=[])
    assert result.overall_score == 0.65


def test_python_evaluator_writes_traces(tmp_path):
    """Test that evaluator writes trace files."""
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()

    eval_script = tmp_path / "evaluate.py"
    eval_script.write_text(textwrap.dedent("""\
        import json, sys
        print(json.dumps({"overall_score": 0.5}))
    """))

    evaluator = PythonEvaluator(entry="evaluate.py", timeout=30, cwd=tmp_path)
    evaluator.evaluate(candidate_dir, tasks=[])

    traces_dir = candidate_dir / "traces"
    assert traces_dir.exists()
    assert (traces_dir / "default.stdout").exists()
    assert (traces_dir / "default.exitcode").exists()


def test_python_evaluator_timeout(tmp_path):
    """Test that evaluator handles timeout gracefully."""
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()

    eval_script = tmp_path / "evaluate.py"
    eval_script.write_text(textwrap.dedent("""\
        import time, sys
        time.sleep(60)
        print("0.99")
    """))

    evaluator = PythonEvaluator(entry="evaluate.py", timeout=1, cwd=tmp_path)
    result = evaluator.evaluate(candidate_dir, tasks=[])
    assert result.overall_score == 0.0
