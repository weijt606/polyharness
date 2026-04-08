"""Trace Collector — records Agent usage data for online evolution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DEFAULT_STORE_DIR = Path.home() / ".polyharness" / "traces"


@dataclass
class TraceRecord:
    """A single recorded Agent execution trace."""

    id: str
    agent: str
    command: list[str]
    exit_code: int
    duration: float
    score: float | None
    timestamp: str
    workspace: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TraceStats:
    """Summary statistics for collected traces."""

    total: int = 0
    scored: int = 0
    mean_score: float | None = None
    latest_score: float | None = None
    agents: dict[str, int] = field(default_factory=dict)


class Collector:
    """Collects and manages Agent execution traces.

    Traces are stored in ``~/.polyharness/traces/`` by default, with one
    sub-directory per trace containing ``meta.json`` and optional output files.
    """

    def __init__(self, store_dir: str | Path | None = None):
        self.store_dir = Path(store_dir) if store_dir else DEFAULT_STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent: str,
        command: list[str],
        exit_code: int,
        duration: float,
        stdout: str | None = None,
        stderr: str | None = None,
        score: float | None = None,
        workspace: str | None = None,
        record_output: bool = True,
    ) -> str:
        """Record a single trace and return its ``trace_id``."""
        trace_id = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"

        trace = TraceRecord(
            id=trace_id,
            agent=agent,
            command=command,
            exit_code=exit_code,
            duration=duration,
            score=score,
            timestamp=datetime.now(timezone.utc).isoformat(),
            workspace=workspace,
        )

        trace_dir = self.store_dir / trace_id
        trace_dir.mkdir(parents=True, exist_ok=True)

        with open(trace_dir / "meta.json", "w") as f:
            json.dump(trace.to_dict(), f, indent=2)

        if record_output:
            if stdout is not None:
                (trace_dir / "stdout.txt").write_text(stdout)
            if stderr is not None:
                (trace_dir / "stderr.txt").write_text(stderr)

        return trace_id

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def list_traces(self, limit: int | None = None) -> list[TraceRecord]:
        """Return traces sorted by timestamp (newest first)."""
        traces: list[TraceRecord] = []
        if not self.store_dir.exists():
            return traces

        for d in self.store_dir.iterdir():
            meta = d / "meta.json"
            if not meta.is_file():
                continue
            with open(meta) as f:
                data = json.load(f)
            traces.append(TraceRecord(**{k: v for k, v in data.items() if k in TraceRecord.__dataclass_fields__}))

        traces.sort(key=lambda t: t.timestamp, reverse=True)
        if limit:
            traces = traces[:limit]

        return traces

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        """Get a single trace by ID."""
        meta = self.store_dir / trace_id / "meta.json"
        if not meta.is_file():
            return None
        with open(meta) as f:
            data = json.load(f)
        return TraceRecord(**{k: v for k, v in data.items() if k in TraceRecord.__dataclass_fields__})

    def get_trace_output(self, trace_id: str) -> dict[str, str]:
        """Return stdout/stderr for a trace if recorded."""
        trace_dir = self.store_dir / trace_id
        result: dict[str, str] = {}
        for name in ("stdout.txt", "stderr.txt"):
            path = trace_dir / name
            if path.is_file():
                result[name.replace(".txt", "")] = path.read_text()
        return result

    def get_scores(self, window: int = 20) -> list[float]:
        """Return the most recent scored values (oldest → newest)."""
        traces = self.list_traces(limit=window * 3)  # over-fetch to fill window
        scores = [t.score for t in reversed(traces) if t.score is not None]
        return scores[-window:]

    def stats(self) -> TraceStats:
        """Compute summary statistics."""
        traces = self.list_traces()
        scored = [t for t in traces if t.score is not None]

        agents: dict[str, int] = {}
        for t in traces:
            agents[t.agent] = agents.get(t.agent, 0) + 1

        mean_score = None
        if scored:
            mean_score = sum(t.score for t in scored) / len(scored)  # type: ignore[arg-type]

        return TraceStats(
            total=len(traces),
            scored=len(scored),
            mean_score=round(mean_score, 4) if mean_score is not None else None,
            latest_score=scored[0].score if scored else None,
            agents=agents,
        )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self, keep_recent: int = 0) -> int:
        """Remove traces, optionally keeping the N most recent. Returns count removed."""
        import shutil

        traces = self.list_traces()
        to_remove = traces[keep_recent:] if keep_recent > 0 else traces
        removed = 0
        for t in to_remove:
            trace_dir = self.store_dir / t.id
            if trace_dir.is_dir():
                shutil.rmtree(trace_dir)
                removed += 1
        return removed

    def count_since_last_evolution(self) -> int:
        """Count traces recorded since the last evolution run."""
        evo_log = self.store_dir.parent / "evolution_log.jsonl"
        last_ts = None
        if evo_log.is_file():
            lines = evo_log.read_text().strip().splitlines()
            if lines:
                last_entry = json.loads(lines[-1])
                last_ts = last_entry.get("timestamp")

        if last_ts is None:
            return len(self.list_traces())

        count = 0
        for t in self.list_traces():
            if t.timestamp > last_ts:
                count += 1
            else:
                break
        return count
