"""Tests for the compare command — code diff + task delta."""

import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from poly_harness.cli import main, _format_delta, _collect_files


def _make_workspace_with_candidates(root: Path) -> Path:
    """Create a minimal workspace with two candidates."""
    from poly_harness.workspace import Workspace

    ws = Workspace.init(root=root, agent_backend="local")

    # iter_0: base candidate
    c0 = ws.candidate_path(0)
    c0.mkdir(parents=True, exist_ok=True)
    (c0 / "harness.py").write_text('words = ["good", "bad"]\n')
    (c0 / "score.json").write_text(
        json.dumps(
            {
                "iteration": 0,
                "overall_score": 0.6,
                "task_scores": {"t1": 1.0, "t2": 0.0, "t3": 1.0},
            }
        )
    )

    # iter_1: improved candidate
    c1 = ws.candidate_path(1)
    c1.mkdir(parents=True, exist_ok=True)
    (c1 / "harness.py").write_text('words = ["good", "bad", "great", "awful"]\n')
    (c1 / "score.json").write_text(
        json.dumps(
            {
                "iteration": 1,
                "overall_score": 1.0,
                "task_scores": {"t1": 1.0, "t2": 1.0, "t3": 1.0},
            }
        )
    )

    return root


def test_compare_shows_delta():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        ws_path = _make_workspace_with_candidates(Path(tmp) / "ws")
        result = runner.invoke(main, ["compare", "0", "1", "--workspace", str(ws_path)])
        assert result.exit_code == 0
        # Should contain overall scores
        assert "0.6" in result.output
        assert "1.0" in result.output
        # Should contain delta column header
        assert "Δ" in result.output
        # Should contain task summary
        assert "improved" in result.output


def test_compare_shows_code_diff():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        ws_path = _make_workspace_with_candidates(Path(tmp) / "ws")
        result = runner.invoke(main, ["compare", "0", "1", "--workspace", str(ws_path)])
        assert result.exit_code == 0
        assert "Code Diff" in result.output
        assert "harness.py" in result.output
        # Diff content: old line removed, new line added
        assert '"good", "bad"' in result.output


def test_compare_no_diff_flag():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        ws_path = _make_workspace_with_candidates(Path(tmp) / "ws")
        result = runner.invoke(
            main, ["compare", "0", "1", "--no-diff", "--workspace", str(ws_path)]
        )
        assert result.exit_code == 0
        assert "Code Diff" not in result.output


def test_compare_iter_prefix():
    """Accept 'iter_0' and 'iter_1' syntax."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp:
        ws_path = _make_workspace_with_candidates(Path(tmp) / "ws")
        result = runner.invoke(
            main, ["compare", "iter_0", "iter_1", "--workspace", str(ws_path)]
        )
        assert result.exit_code == 0
        assert "0.6" in result.output


def test_format_delta():
    assert "+0.35" in _format_delta(0.65, 1.0)
    assert "-0.20" in _format_delta(1.0, 0.8)
    assert "0.00" in _format_delta(0.5, 0.5)
    assert "—" == _format_delta(None, 1.0)


def test_collect_files_skips_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "harness.py").write_text("x")
        (d / "score.json").write_text("x")
        (d / "metadata.json").write_text("x")
        cache = d / "__pycache__"
        cache.mkdir()
        (cache / "foo.pyc").write_text("x")
        traces = d / "traces"
        traces.mkdir()
        (traces / "log.txt").write_text("x")

        files = _collect_files(d, {"score.json", "metadata.json", "__pycache__", "traces"})
        assert files == ["harness.py"]
