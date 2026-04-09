"""Hermes Agent CLI adapter.

Invokes the Nous Research `hermes` CLI in single-query mode (-q).
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter


class HermesAdapter(CLIAdapter):
    """Adapter for the Hermes Agent CLI (`hermes`)."""

    @property
    def name(self) -> str:
        return "hermes"

    @property
    def default_binary(self) -> str:
        return "hermes"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "chat",
            "-q",                # single-query mode (non-interactive)
            prompt,
        ]
