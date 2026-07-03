"""Shared workspace tools for API-based proposers (Anthropic + OpenAI-compatible).

Single source of truth for the file tools exposed to proposer models, so the
security-sensitive parts exist exactly once:

- Path containment resolves both ends and uses `Path.is_relative_to` — a plain
  `str.startswith` check lets `candidates/iter_1` match `candidates/iter_10`.
- Evaluation artifacts (`score.json`, `metadata.json`) are write-protected even
  inside the candidate directory; the evaluator owns them.
- There is deliberately NO shell tool. A first-token allowlist in front of
  `shell=True` is not a sandbox (`echo x; rm -rf .`, `ls > score.json`).
  `file_search` covers the legitimate grep-style uses in pure Python.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Files the evaluator owns; proposers must never overwrite them.
PROTECTED_FILENAMES = frozenset({"score.json", "metadata.json"})

# Tool schemas in a neutral shape; adapted per API protocol below.
_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "file_read",
        "description": "Read a file from the workspace. Returns its content.",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path from the workspace root.",
            },
        },
        "required": ["path"],
    },
    {
        "name": "file_write",
        "description": "Write content to a file in the current candidate directory.",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path within the candidate directory.",
            },
            "content": {"type": "string", "description": "Full content to write."},
        },
        "required": ["path", "content"],
    },
    {
        "name": "list_dir",
        "description": "List files and directories at the given workspace path.",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path from the workspace root.",
            },
        },
        "required": ["path"],
    },
    {
        "name": "file_search",
        "description": (
            "Search workspace files for a regex pattern (like grep -rn). "
            "Returns matching lines as `path:lineno: text`."
        ),
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression to search for."},
            "path": {
                "type": "string",
                "description": "Relative directory (or file) to search under. Default: workspace root.",
            },
        },
        "required": ["pattern"],
    },
]


def anthropic_tool_definitions() -> list[dict[str, Any]]:
    """Tool definitions in Anthropic Messages API shape."""
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "input_schema": {
                "type": "object",
                "properties": s["properties"],
                "required": s["required"],
            },
        }
        for s in _TOOL_SPECS
    ]


def openai_tool_definitions() -> list[dict[str, Any]]:
    """Tool definitions in OpenAI chat-completions function shape."""
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": {
                    "type": "object",
                    "properties": s["properties"],
                    "required": s["required"],
                },
            },
        }
        for s in _TOOL_SPECS
    ]


class WorkspaceToolkit:
    """Executes proposer tool calls against the workspace with containment."""

    MAX_READ_CHARS = 100_000
    MAX_SEARCH_RESULTS = 100
    MAX_SEARCH_FILE_BYTES = 1_000_000

    def __init__(self, workspace_root: Path, candidate_dir: Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.candidate_dir = Path(candidate_dir).resolve()

    def execute(self, name: str, tool_input: dict) -> str:
        """Dispatch a tool call; always returns a string (errors included)."""
        try:
            if name == "file_read":
                return self.read(tool_input.get("path", ""))
            if name == "file_write":
                return self.write(tool_input.get("path", ""), tool_input.get("content", ""))
            if name == "list_dir":
                return self.list_dir(tool_input.get("path", ""))
            if name == "file_search":
                return self.search(tool_input.get("pattern", ""), tool_input.get("path", "."))
            return f"Error: unknown tool '{name}'"
        except Exception as e:  # noqa: BLE001 — tool errors go back to the model
            return f"Error: {e}"

    # -- individual tools ---------------------------------------------------

    def read(self, rel_path: str) -> str:
        target = self._resolve_in(self.workspace_root, rel_path)
        if target is None:
            return "Error: path outside workspace"
        if not target.exists():
            return f"Error: file not found: {rel_path}"
        if target.is_dir():
            return "Error: path is a directory, use list_dir instead"
        content = target.read_text(errors="replace")
        if len(content) > self.MAX_READ_CHARS:
            return content[: self.MAX_READ_CHARS] + "\n... (truncated)"
        return content

    def write(self, rel_path: str, content: str) -> str:
        target = self._resolve_in(self.candidate_dir, rel_path)
        if target is None:
            return "Error: can only write inside candidate directory"
        if target.name in PROTECTED_FILENAMES:
            return f"Error: {target.name} is written by the evaluator and cannot be modified"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} bytes to {rel_path}"

    def list_dir(self, rel_path: str) -> str:
        target = self._resolve_in(self.workspace_root, rel_path)
        if target is None:
            return "Error: path outside workspace"
        if not target.exists():
            return f"Error: path not found: {rel_path}"
        if not target.is_dir():
            return "Error: not a directory"
        lines = [f"{e.name}{'/' if e.is_dir() else ''}" for e in sorted(target.iterdir())[:200]]
        return "\n".join(lines) if lines else "(empty directory)"

    def search(self, pattern: str, rel_path: str = ".") -> str:
        if not pattern:
            return "Error: empty pattern"
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex: {e}"
        base = self._resolve_in(self.workspace_root, rel_path)
        if base is None:
            return "Error: path outside workspace"
        if not base.exists():
            return f"Error: path not found: {rel_path}"

        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        results: list[str] = []
        for f in files:
            if "__pycache__" in f.parts:
                continue
            try:
                if f.stat().st_size > self.MAX_SEARCH_FILE_BYTES:
                    continue
                text = f.read_text(errors="replace")
            except OSError:
                continue
            if "\x00" in text[:1024]:  # skip binary
                continue
            rel = f.relative_to(self.workspace_root)
            for lineno, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    results.append(f"{rel}:{lineno}: {line.strip()[:300]}")
                    if len(results) >= self.MAX_SEARCH_RESULTS:
                        results.append("... (result limit reached)")
                        return "\n".join(results)
        return "\n".join(results) if results else "(no matches)"

    # -- containment ---------------------------------------------------------

    @staticmethod
    def _resolve_in(root: Path, rel_path: str) -> Path | None:
        """Resolve `rel_path` against `root`; None if it escapes `root`."""
        target = (root / rel_path).resolve()
        if target == root or target.is_relative_to(root):
            return target
        return None
