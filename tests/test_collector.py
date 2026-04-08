"""Tests for the Trace Collector (v0.2.0 online evolution)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polyharness.collector import Collector


@pytest.fixture()
def store_dir(tmp_path: Path) -> Path:
    """Provide a temporary trace store directory."""
    d = tmp_path / "traces"
    d.mkdir()
    return d


@pytest.fixture()
def collector(store_dir: Path) -> Collector:
    return Collector(store_dir=store_dir)


class TestCollectorRecord:
    def test_record_creates_trace_dir(self, collector: Collector, store_dir: Path):
        tid = collector.record(
            agent="echo",
            command=["echo", "hello"],
            exit_code=0,
            duration=0.1,
            stdout="hello\n",
        )
        trace_dir = store_dir / tid
        assert trace_dir.is_dir()
        assert (trace_dir / "meta.json").is_file()
        assert (trace_dir / "stdout.txt").is_file()

    def test_record_meta_content(self, collector: Collector, store_dir: Path):
        tid = collector.record(
            agent="test-agent",
            command=["test-agent", "--flag"],
            exit_code=1,
            duration=2.5,
            score=0.85,
            workspace="/tmp/ws",
        )
        meta = json.loads((store_dir / tid / "meta.json").read_text())
        assert meta["agent"] == "test-agent"
        assert meta["exit_code"] == 1
        assert meta["duration"] == 2.5
        assert meta["score"] == 0.85
        assert meta["workspace"] == "/tmp/ws"

    def test_record_no_output(self, collector: Collector, store_dir: Path):
        tid = collector.record(
            agent="echo",
            command=["echo"],
            exit_code=0,
            duration=0.1,
            record_output=False,
            stdout="should not be saved",
        )
        trace_dir = store_dir / tid
        assert not (trace_dir / "stdout.txt").exists()


class TestCollectorQuery:
    def test_list_empty(self, collector: Collector):
        assert collector.list_traces() == []

    def test_list_returns_newest_first(self, collector: Collector):
        import time

        collector.record(agent="a", command=["a"], exit_code=0, duration=0.1)
        time.sleep(0.05)  # ensure distinct microsecond timestamps
        collector.record(agent="b", command=["b"], exit_code=0, duration=0.2)
        traces = collector.list_traces()
        assert len(traces) == 2
        # Newest first (sorted by ISO timestamp)
        assert traces[0].agent == "b"
        assert traces[1].agent == "a"

    def test_list_with_limit(self, collector: Collector):
        for i in range(5):
            collector.record(agent="a", command=["a"], exit_code=0, duration=0.1)
        assert len(collector.list_traces(limit=3)) == 3

    def test_get_trace(self, collector: Collector):
        tid = collector.record(
            agent="x", command=["x", "1"], exit_code=0, duration=1.0, score=0.5
        )
        t = collector.get_trace(tid)
        assert t is not None
        assert t.agent == "x"
        assert t.score == 0.5

    def test_get_trace_not_found(self, collector: Collector):
        assert collector.get_trace("nonexistent") is None

    def test_get_trace_output(self, collector: Collector):
        tid = collector.record(
            agent="a",
            command=["a"],
            exit_code=0,
            duration=0.1,
            stdout="out",
            stderr="err",
        )
        output = collector.get_trace_output(tid)
        assert output["stdout"] == "out"
        assert output["stderr"] == "err"

    def test_get_scores(self, collector: Collector):
        import time

        scores_in = [0.3, 0.5, 0.7, 0.9]
        for s in scores_in:
            collector.record(agent="a", command=["a"], exit_code=0, duration=0.1, score=s)
            time.sleep(0.02)  # ensure distinct timestamps for ordering
        scores_out = collector.get_scores(window=10)
        assert scores_out == scores_in

    def test_get_scores_skips_unscored(self, collector: Collector):
        collector.record(agent="a", command=["a"], exit_code=0, duration=0.1, score=0.5)
        collector.record(agent="a", command=["a"], exit_code=0, duration=0.1)  # no score
        collector.record(agent="a", command=["a"], exit_code=0, duration=0.1, score=0.8)
        scores = collector.get_scores(window=10)
        assert scores == [0.5, 0.8]


class TestCollectorStats:
    def test_empty_stats(self, collector: Collector):
        s = collector.stats()
        assert s.total == 0
        assert s.scored == 0
        assert s.mean_score is None

    def test_stats_with_data(self, collector: Collector):
        collector.record(agent="a", command=["a"], exit_code=0, duration=0.1, score=0.4)
        collector.record(agent="a", command=["a"], exit_code=0, duration=0.2, score=0.6)
        collector.record(agent="b", command=["b"], exit_code=1, duration=0.3)
        s = collector.stats()
        assert s.total == 3
        assert s.scored == 2
        assert s.mean_score == 0.5
        assert s.agents == {"a": 2, "b": 1}


class TestCollectorClear:
    def test_clear_all(self, collector: Collector):
        for _ in range(3):
            collector.record(agent="a", command=["a"], exit_code=0, duration=0.1)
        removed = collector.clear()
        assert removed == 3
        assert collector.list_traces() == []

    def test_clear_keep_recent(self, collector: Collector):
        import time

        for _ in range(5):
            collector.record(agent="a", command=["a"], exit_code=0, duration=0.1)
            time.sleep(0.01)
        removed = collector.clear(keep_recent=2)
        assert removed == 3
        assert len(collector.list_traces()) == 2
