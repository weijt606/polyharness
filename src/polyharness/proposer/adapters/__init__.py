"""CLI agent adapter registry.

Provides a mapping from backend name to adapter class, so the CLIProposer
can look up the right adapter at runtime.
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter, CLIResult
from polyharness.proposer.adapters.claude_code import ClaudeCodeAdapter
from polyharness.proposer.adapters.claw_code import ClawCodeAdapter
from polyharness.proposer.adapters.codex import CodexAdapter
from polyharness.proposer.adapters.hermes import HermesAdapter
from polyharness.proposer.adapters.opencode import OpenCodeAdapter

ADAPTER_REGISTRY: dict[str, type[CLIAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "claw-code": ClawCodeAdapter,
    "codex": CodexAdapter,
    "hermes": HermesAdapter,
    "opencode": OpenCodeAdapter,
}


def get_adapter(backend: str) -> CLIAdapter:
    """Instantiate a CLI adapter by backend name.

    Raises KeyError if the backend is not registered.
    """
    cls = ADAPTER_REGISTRY.get(backend)
    if cls is None:
        supported = ", ".join(sorted(ADAPTER_REGISTRY))
        raise KeyError(f"Unknown CLI adapter '{backend}'. Registered: {supported}")
    return cls()


__all__ = [
    "CLIAdapter",
    "CLIResult",
    "ClaudeCodeAdapter",
    "ClawCodeAdapter",
    "CodexAdapter",
    "HermesAdapter",
    "OpenCodeAdapter",
    "ADAPTER_REGISTRY",
    "get_adapter",
]
