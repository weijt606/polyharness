"""LessonBook — the loop's distilled evolution memory.

The Meta-Harness insight is that non-Markovian search (full diagnostic history)
beats blind retries. Raw history is already on disk, but a proposer has a
limited context budget: reading forty candidates' traces every iteration is
expensive and lossy. The LessonBook maintains a compact, structured digest —
one verdict line per iteration (what changed, what happened to the score,
which backend proposed it) — appended to `summary/lessons.jsonl` and rendered
to `summary/LESSONS.md` for the proposer to read first.

This is mechanical distillation (no extra LLM calls): deterministic,
reproducible, and free.
"""

from __future__ import annotations

import json
from pathlib import Path

_MAX_SUMMARY_CHARS = 400
_RENDERED_LESSONS = 30  # most recent lessons kept in LESSONS.md


class LessonBook:
    """Append-only iteration verdicts + a rendered markdown digest."""

    def __init__(self, workspace_root: Path):
        self.summary_dir = Path(workspace_root) / "summary"
        self.jsonl_path = self.summary_dir / "lessons.jsonl"
        self.md_path = self.summary_dir / "LESSONS.md"

    def record(
        self,
        *,
        iteration: int,
        parent: int | None,
        verdict: str,  # improved | regressed | tied | failed | duplicate
        score: float | None = None,
        parent_score: float | None = None,
        changes_summary: str = "",
        backend: str | None = None,
        note: str = "",
    ) -> None:
        """Append one lesson and re-render the markdown digest."""
        self.summary_dir.mkdir(exist_ok=True)
        lesson = {
            "iteration": iteration,
            "parent": parent,
            "verdict": verdict,
            "score": score,
            "parent_score": parent_score,
            "delta": (
                round(score - parent_score, 6)
                if score is not None and parent_score is not None
                else None
            ),
            "backend": backend,
            "changes_summary": changes_summary[:_MAX_SUMMARY_CHARS],
            "note": note[:_MAX_SUMMARY_CHARS],
        }
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(lesson, ensure_ascii=False) + "\n")
        self._render()

    def load(self) -> list[dict]:
        if not self.jsonl_path.exists():
            return []
        lessons = []
        for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lessons.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a truncated tail line
        return lessons

    def _render(self) -> None:
        lessons = self.load()[-_RENDERED_LESSONS:]
        if not lessons:
            return

        worked = [ls for ls in lessons if ls["verdict"] == "improved"]
        failed = [ls for ls in lessons if ls["verdict"] in ("regressed", "failed")]
        other = [ls for ls in lessons if ls["verdict"] in ("tied", "duplicate")]

        def fmt(ls: dict) -> str:
            delta = f" (Δ{ls['delta']:+.4f})" if ls.get("delta") is not None else ""
            backend = f" [{ls['backend']}]" if ls.get("backend") else ""
            summary = ls.get("changes_summary") or ls.get("note") or "(no summary)"
            summary = " ".join(summary.split())  # collapse whitespace/newlines
            return f"- iter_{ls['iteration']}{backend}{delta}: {summary}"

        parts = [
            "# Lessons from previous iterations",
            "",
            "Auto-generated digest of the search so far. Read this before",
            "exploring raw traces — it tells you which directions already",
            "paid off and which already failed.",
            "",
        ]
        if worked:
            parts += ["## What improved the score", *map(fmt, worked), ""]
        if failed:
            parts += [
                "## What regressed or failed (do not repeat without a new reason)",
                *map(fmt, failed),
                "",
            ]
        if other:
            parts += ["## Neutral / duplicates", *map(fmt, other), ""]

        self.md_path.write_text("\n".join(parts), encoding="utf-8")
