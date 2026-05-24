"""Tests for SearchLog."""


from polyharness.search_log import LogEntry, SearchLog


def test_search_log_append(tmp_path):
    log_file = tmp_path / "search_log.jsonl"
    log_file.touch()

    log = SearchLog(log_file)
    assert len(log) == 0

    log.append(iteration=0, parent=None, score=0.45)
    assert len(log) == 1
    assert log.best_score == 0.45
    assert log.best_iteration == 0

    log.append(iteration=1, parent=0, score=0.60)
    assert len(log) == 2
    assert log.best_score == 0.60
    assert log.best_iteration == 1


def test_search_log_persistence(tmp_path):
    log_file = tmp_path / "search_log.jsonl"
    log_file.touch()

    log = SearchLog(log_file)
    log.append(iteration=0, parent=None, score=0.5)
    log.append(iteration=1, parent=0, score=0.7, task_scores={"t1": 0.8, "t2": 0.6})

    # Reload from file
    log2 = SearchLog(log_file)
    assert len(log2) == 2
    assert log2.best_score == 0.7
    assert log2.entries[1].task_scores == {"t1": 0.8, "t2": 0.6}


def test_search_log_best_so_far(tmp_path):
    log_file = tmp_path / "search_log.jsonl"
    log_file.touch()

    log = SearchLog(log_file)
    log.append(iteration=0, parent=None, score=0.5)
    log.append(iteration=1, parent=0, score=0.3)
    log.append(iteration=2, parent=0, score=0.8)

    assert log.entries[0].best_so_far == 0.5
    assert log.entries[1].best_so_far == 0.5
    assert log.entries[2].best_so_far == 0.8


def test_log_entry_roundtrip():
    entry = LogEntry(iteration=3, parent=1, score=0.72, best_so_far=0.72, task_scores={"a": 0.8})
    line = entry.to_json()
    restored = LogEntry.from_json(line)
    assert restored.iteration == 3
    assert restored.parent == 1
    assert restored.score == 0.72
    assert restored.task_scores == {"a": 0.8}


def test_pareto_win_counts(tmp_path):
    log = SearchLog(tmp_path / "search_log.jsonl")
    log.append(0, None, 0.5, {"A": 0.5, "B": 0.5})
    log.append(1, 0, 0.5, {"A": 0.9, "B": 0.1})  # wins task A
    log.append(2, 0, 0.5, {"A": 0.1, "B": 0.9})  # wins task B

    counts = log.pareto_win_counts()
    # iter_0 wins nothing; iter_1 and iter_2 each win one task.
    assert set(counts) == {1, 2}
    assert counts[1] == 1
    assert counts[2] == 1


def test_pareto_win_counts_empty_without_task_scores(tmp_path):
    log = SearchLog(tmp_path / "search_log.jsonl")
    log.append(0, None, 0.3, {})
    log.append(1, 0, 0.5, {})
    assert log.pareto_win_counts() == {}
