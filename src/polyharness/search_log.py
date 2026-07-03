"""SearchLog — append-only JSONL log for the optimization search."""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LogEntry:
    """A single search log entry.

    `status` makes the log a full event stream: failed and duplicate-skipped
    iterations are recorded too (previously they vanished, so resume undercounted
    patience and the bandit lost their signal). Only `evaluated` entries carry a
    meaningful score.
    """

    iteration: int
    parent: int | None
    score: float
    best_so_far: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    task_scores: dict[str, float] = field(default_factory=dict)
    status: str = "evaluated"  # evaluated | failed | skipped_duplicate
    proposer_backend: str | None = None
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> LogEntry:
        data = json.loads(line)
        # Ignore unknown fields so logs written by newer versions still load.
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class SearchLog:
    """Append-only JSONL search log backed by a file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: list[LogEntry] = []
        if self.path.exists() and self.path.stat().st_size > 0:
            self._load()

    def _load(self) -> None:
        self._entries = []
        with open(self.path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    self._entries.append(LogEntry.from_json(line))
                except (json.JSONDecodeError, TypeError, ValueError):
                    # A truncated line (e.g. the process was killed mid-write)
                    # must not brick resume/best/apply forever — skip it.
                    warnings.warn(
                        f"Skipping corrupt search log line {lineno} in {self.path}",
                        stacklevel=2,
                    )

    def append(
        self,
        iteration: int,
        parent: int | None,
        score: float,
        task_scores: dict[str, float] | None = None,
        status: str = "evaluated",
        proposer_backend: str | None = None,
        note: str = "",
    ) -> LogEntry:
        """Append a new entry and flush to disk."""
        best = max(score, self.best_score) if self._entries else score
        entry = LogEntry(
            iteration=iteration,
            parent=parent,
            score=score,
            best_so_far=best,
            task_scores=task_scores or {},
            status=status,
            proposer_backend=proposer_backend,
            note=note,
        )
        self._entries.append(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")
            f.flush()
        return entry

    @property
    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    @property
    def evaluated_entries(self) -> list[LogEntry]:
        """Entries that carry a real score (failed/skipped excluded)."""
        return [e for e in self._entries if e.status == "evaluated"]

    @property
    def best_score(self) -> float:
        scored = self.evaluated_entries
        if not scored:
            return 0.0
        return max(e.score for e in scored)

    @property
    def best_iteration(self) -> int:
        scored = self.evaluated_entries
        if not scored:
            return 0
        return max(scored, key=lambda e: e.score).iteration

    def pareto_win_counts(self) -> dict[int, int]:
        """Map each Pareto-frontier iteration to the number of tasks it wins.

        A candidate is on the frontier if it achieves the top score on at
        least one individual task (GEPA-style per-task winners). The values
        are how many tasks each frontier member wins. Returns an empty dict
        when no per-task scores are recorded.
        """
        entries = [e for e in self.evaluated_entries if e.task_scores]
        if not entries:
            return {}

        task_names: set[str] = set()
        for e in entries:
            task_names.update(e.task_scores.keys())

        eps = 1e-9
        counts: dict[int, int] = {}
        for task in task_names:
            best = max(e.task_scores.get(task, float("-inf")) for e in entries)
            for e in entries:
                if e.task_scores.get(task, float("-inf")) >= best - eps:
                    counts[e.iteration] = counts.get(e.iteration, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self._entries)
