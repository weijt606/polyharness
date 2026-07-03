"""Claude Code CLI adapter.

Invokes the official `claude` CLI in print mode (-p).
Requires an active Claude Code subscription.

Verified against Claude Code (July 2026):
- `-p` headless mode and `--output-format text` are current.
- `--permission-mode acceptEdits` is REQUIRED for the agent to write files
  non-interactively (auto-approves Read/Edit/Write); without it, headless edits
  are blocked. `acceptEdits` still gates arbitrary Bash/network (least-privilege,
  appropriate for the isolated workspace).
- The pinned model comes from the central default table in
  `polyharness.config` (currently Opus 4.8; full name for reproducibility).
"""

from __future__ import annotations

from polyharness.config import DEFAULT_CLAUDE_CODE_MODEL
from polyharness.proposer.adapters.base import CLIAdapter

# Pinned Proposer model for the Claude Code backend (kept as a module-level
# alias for backwards compatibility; the value lives in config).
CLAUDE_CODE_MODEL = DEFAULT_CLAUDE_CODE_MODEL


class ClaudeCodeAdapter(CLIAdapter):
    """Adapter for the Claude Code CLI (`claude`)."""

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def default_binary(self) -> str:
        return "claude"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "-p",                                # print mode (non-interactive)
            prompt,
            "--model", CLAUDE_CODE_MODEL,        # pinned via config defaults
            "--permission-mode", "acceptEdits",  # auto-approve file edits (headless)
            "--output-format", "text",
        ]
