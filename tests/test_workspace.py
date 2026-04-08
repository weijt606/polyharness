"""Tests for workspace initialization and structure."""

import json
import tempfile
from pathlib import Path

from polyharness.workspace import Workspace


def test_workspace_init():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ws"
        ws = Workspace.init(root=root, agent_backend="api")

        assert ws.root.exists()
        assert ws.is_initialized()
        assert ws.candidates_dir.is_dir()
        assert ws.base_harness_dir.is_dir()
        assert ws.search_log_path.exists()
        assert (ws.root / "config.yaml").exists()


def test_workspace_load_config():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ws"
        ws = Workspace.init(root=root, agent_backend="claude-code")
        cfg = ws.load_config()

        assert cfg.proposer.backend == "claude-code"


def test_workspace_load_config_local_backend():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ws"
        ws = Workspace.init(root=root, agent_backend="local")
        cfg = ws.load_config()

        assert cfg.proposer.backend == "local"


def test_workspace_candidate_path():
    ws = Workspace("/tmp/fake-ws")
    assert ws.candidate_path(3) == ws.candidates_dir / "iter_3"


def test_workspace_not_initialized():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(tmp)
        assert not ws.is_initialized()


# ------------------------------------------------------------------
# Agent instruction injection
# ------------------------------------------------------------------


def test_init_injects_claude_md():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace.init(Path(tmp) / "ws", agent_backend="claude-code")
        claude_md = ws.root / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "PolyHarness Proposer" in content
        assert "claude-code" in content


def test_init_injects_claw_md():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace.init(Path(tmp) / "ws", agent_backend="claw-code")
        assert (ws.root / "CLAW.md").exists()


def test_init_injects_codex_md():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace.init(Path(tmp) / "ws", agent_backend="codex")
        assert (ws.root / "CODEX.md").exists()


def test_init_injects_opencode_md():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace.init(Path(tmp) / "ws", agent_backend="opencode")
        assert (ws.root / "OPENCODE.md").exists()


def test_init_no_injection_for_api():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace.init(Path(tmp) / "ws", agent_backend="api")
        assert not (ws.root / "CLAUDE.md").exists()
        assert not (ws.root / "CLAW.md").exists()


def test_init_does_not_overwrite_existing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "ws"
        root.mkdir()
        custom = root / "CLAUDE.md"
        custom.write_text("# My custom instructions\n")

        Workspace.init(root, agent_backend="claude-code")
        assert custom.read_text() == "# My custom instructions\n"


# ------------------------------------------------------------------
# Apply best harness
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Init with --task-dir / --eval-script / --base-harness
# ------------------------------------------------------------------


def test_init_with_base_harness(tmp_path):
    # Create a source base harness
    src = tmp_path / "src_harness"
    src.mkdir()
    (src / "harness.py").write_text("def solve(): pass\n")
    (src / "helpers.py").write_text("# helpers\n")

    ws = Workspace.init(tmp_path / "ws", base_harness=src)
    assert (ws.base_harness_dir / "harness.py").exists()
    assert (ws.base_harness_dir / "helpers.py").exists()
    assert (ws.base_harness_dir / "harness.py").read_text() == "def solve(): pass\n"


def test_init_with_task_dir(tmp_path):
    # Create a task dir structure
    td = tmp_path / "my_task"
    td.mkdir()
    (td / "tasks").mkdir()
    (td / "tasks" / "test_cases.json").write_text('[{"q": "hi"}]')
    (td / "evaluate.py").write_text("# eval\n")

    ws = Workspace.init(tmp_path / "ws", task_dir=td)

    # Tasks should be copied
    assert (ws.root / "tasks" / "test_cases.json").exists()
    assert (ws.root / "tasks" / "test_cases.json").read_text() == '[{"q": "hi"}]'
    # evaluate.py should also be copied (auto-detected from task_dir)
    assert (ws.root / "evaluate.py").exists()
    assert (ws.root / "evaluate.py").read_text() == "# eval\n"


def test_init_with_eval_script(tmp_path):
    es = tmp_path / "my_eval.py"
    es.write_text("# custom eval\n")

    ws = Workspace.init(tmp_path / "ws", eval_script=es)
    assert (ws.root / "evaluate.py").exists()
    assert (ws.root / "evaluate.py").read_text() == "# custom eval\n"


def test_init_with_all_options(tmp_path):
    # base harness
    bh = tmp_path / "bh"
    bh.mkdir()
    (bh / "harness.py").write_text("# base\n")

    # task dir
    td = tmp_path / "td"
    td.mkdir()
    (td / "tasks").mkdir()
    (td / "tasks" / "cases.json").write_text("[]")

    # eval script
    es = tmp_path / "score.py"
    es.write_text("# scorer\n")

    ws = Workspace.init(
        tmp_path / "ws",
        agent_backend="local",
        base_harness=bh,
        task_dir=td,
        eval_script=es,
    )
    assert (ws.base_harness_dir / "harness.py").read_text() == "# base\n"
    assert (ws.root / "tasks" / "cases.json").exists()
    assert (ws.root / "evaluate.py").read_text() == "# scorer\n"
    cfg = ws.load_config()
    assert cfg.proposer.backend == "local"
    assert cfg.evaluator.entry == "evaluate.py"


# ------------------------------------------------------------------
# Template initialization
# ------------------------------------------------------------------


def test_init_with_template(tmp_path):
    ws = Workspace.init(tmp_path / "ws", agent_backend="api", template="text-classification")
    assert ws.is_initialized()
    assert (ws.base_harness_dir / "harness.py").exists()
    assert (ws.root / "tasks" / "test_cases.json").exists()
    assert (ws.root / "evaluate.py").exists()
    cfg = ws.load_config()
    assert cfg.proposer.backend == "api"


def test_init_template_unknown(tmp_path):
    import click
    import pytest

    with pytest.raises(click.BadParameter, match="Unknown template"):
        Workspace.init(tmp_path / "ws", template="nonexistent")


def test_init_template_conflicts_with_base_harness(tmp_path):
    import click
    import pytest

    with pytest.raises(click.UsageError, match="--template cannot be combined"):
        Workspace.init(tmp_path / "ws", template="text-classification", base_harness="/tmp")


# ------------------------------------------------------------------
# Apply best harness
# ------------------------------------------------------------------


def test_apply_best(tmp_path):
    ws = Workspace.init(tmp_path / "ws")

    # Create a candidate with a harness file
    iter0 = ws.candidate_path(0)
    iter0.mkdir(parents=True)
    (iter0 / "harness.py").write_text("# optimized\n")
    (iter0 / "score.json").write_text(json.dumps({"overall_score": 0.9}))
    (iter0 / "metadata.json").write_text("{}")
    (iter0 / "traces").mkdir()
    (iter0 / "traces" / "t.txt").write_text("trace")

    # Add a log entry
    log = ws.search_log()
    log.append(iteration=0, parent=None, score=0.9)

    target = tmp_path / "output"
    best_i, copied = ws.apply_best(target)

    assert best_i == 0
    assert copied == 1  # only harness.py (score.json, metadata.json, traces skipped)
    assert (target / "harness.py").read_text() == "# optimized\n"
    assert not (target / "score.json").exists()
    assert not (target / "traces").exists()
