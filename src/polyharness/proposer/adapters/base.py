"""Base class for CLI agent adapters.

Each adapter knows how to invoke a specific CLI coding agent
(Claude Code, Claw Code, Codex, OpenCode) and parse its output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CLIResult:
    """Parsed result from a CLI agent invocation."""

    stdout: str
    stderr: str
    returncode: int
    changes_summary: str = ""
    extra: dict = field(default_factory=dict)


class CLIAdapter(ABC):
    """Abstract adapter for a CLI-based coding agent."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g. 'claude-code')."""
        ...

    @property
    @abstractmethod
    def default_binary(self) -> str:
        """Default CLI binary name (e.g. 'claude')."""
        ...

    @abstractmethod
    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        """Build the full argv list for the CLI agent.

        Args:
            prompt: The optimization prompt to send.
            cli_path: Override path to the CLI binary (None = use default_binary).

        Returns:
            Command list suitable for subprocess.run().
        """
        ...

    def parse_output(self, stdout: str, stderr: str, returncode: int) -> CLIResult:
        """Parse raw subprocess output into a CLIResult.

        The default implementation treats the full stdout as the changes summary.
        Subclasses can override for JSON or structured output parsing.
        """
        summary = stdout.strip()
        if len(summary) > 2000:
            summary = summary[-2000:]
        return CLIResult(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            changes_summary=summary,
        )

    def env_vars(self) -> dict[str, str]:
        """Extra environment variables to set for the subprocess.

        Returns an empty dict by default. Override if the CLI needs
        specific env vars (e.g. API keys, config paths).
        """
        return {}
