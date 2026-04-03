"""Tests for config loading and serialization."""

import tempfile
from pathlib import Path

from poly_harness.config import PolyHarnessConfig


def test_default_config():
    cfg = PolyHarnessConfig()
    assert cfg.search.max_iterations == 20
    assert cfg.search.early_stop_patience == 5
    assert cfg.proposer.backend == "api"
    assert cfg.evaluator.type == "python"
    assert cfg.harness.language == "python"


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
