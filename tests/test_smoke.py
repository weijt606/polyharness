"""Smoke tests — verify package imports and CLI entrypoint."""

import subprocess
import sys

import poly_harness


def test_version_exists():
    assert poly_harness.__version__


def test_import_config():
    from poly_harness.config import PolyHarnessConfig

    cfg = PolyHarnessConfig()
    assert cfg.search.max_iterations == 20
    assert cfg.proposer.backend == "api"


def test_import_workspace():
    from poly_harness.workspace import Workspace

    ws = Workspace("/tmp/test-ws")
    assert ws.root.name == "test-ws"


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "poly_harness", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "PolyHarness" in result.stdout


def test_cli_version():
    result = subprocess.run(
        [sys.executable, "-m", "poly_harness", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert poly_harness.__version__ in result.stdout
