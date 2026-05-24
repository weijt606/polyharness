"""Tests for config loading and serialization."""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from polyharness.config import PolyHarnessConfig


def test_default_config():
    cfg = PolyHarnessConfig()
    assert cfg.search.max_iterations == 20
    assert cfg.search.early_stop_patience == 5
    assert cfg.proposer.backend == "api"
    assert cfg.proposer.ensemble == []  # single-backend by default
    assert cfg.search.seed is None
    assert cfg.evaluator.type == "python"
    assert cfg.harness.language == "python"


def test_ensemble_accepts_valid_backends():
    cfg = PolyHarnessConfig.model_validate(
        {"proposer": {"ensemble": ["local", "api", "codex"]}}
    )
    assert cfg.proposer.ensemble == ["local", "api", "codex"]


def test_ensemble_rejects_unknown_backend():
    with pytest.raises(ValidationError):
        PolyHarnessConfig.model_validate({"proposer": {"ensemble": ["bogus"]}})


def test_parent_selection_accepts_pareto():
    cfg = PolyHarnessConfig.model_validate({"search": {"parent_selection": "pareto"}})
    assert cfg.search.parent_selection == "pareto"


def test_cascade_defaults_and_roundtrip():
    cfg = PolyHarnessConfig()
    assert cfg.evaluator.cascade is False
    assert cfg.evaluator.cascade_threshold == 0.4
    assert cfg.evaluator.cascade_stage1 == 0

    cfg.evaluator.cascade = True
    cfg.evaluator.cascade_stage1 = 3
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        cfg.to_yaml(path)
        loaded = PolyHarnessConfig.from_yaml(path)
    assert loaded.evaluator.cascade is True
    assert loaded.evaluator.cascade_stage1 == 3


def test_config_roundtrip_yaml():
    cfg = PolyHarnessConfig()
    cfg.proposer.backend = "claude-code"  # type: ignore[assignment]
    cfg.search.max_iterations = 50

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        cfg.to_yaml(path)
        loaded = PolyHarnessConfig.from_yaml(path)

    assert loaded.proposer.backend == "claude-code"
    assert loaded.search.max_iterations == 50
    assert loaded.evaluator.type == "python"


def test_config_from_partial_yaml():
    import yaml

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        with open(path, "w") as f:
            yaml.dump({"search": {"max_iterations": 10}}, f)

        loaded = PolyHarnessConfig.from_yaml(path)

    assert loaded.search.max_iterations == 10
    assert loaded.proposer.backend == "api"  # default preserved
