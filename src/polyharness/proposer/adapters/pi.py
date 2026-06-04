"""Pi coding agent CLI adapter.

Invokes the open-source `pi` agent (earendil-works/pi) in print mode (-p),
a single-shot, non-interactive run that executes its tools and exits.

By design, pi has NO permission popups and NO approval/sandbox flags — in
print mode it edits files in the current working directory autonomously, so
no `--accept-edits`/`--sandbox`/`--yolo` equivalent exists (or is needed).
Isolation is the caller's responsibility; PolyHarness already runs each
candidate in its own workspace directory.

pi auto-reads `AGENTS.md` from the working directory at startup, which is the
instruction file PolyHarness injects for this backend (see workspace.py).

See: https://github.com/earendil-works/pi
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter


class PiAdapter(CLIAdapter):
    """Adapter for the Pi coding agent CLI (`pi`)."""

    @property
    def name(self) -> str:
        return "pi"

    @property
    def default_binary(self) -> str:
        return "pi"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "-p",                # print mode: single-shot, non-interactive, then exit
            prompt,
        ]
