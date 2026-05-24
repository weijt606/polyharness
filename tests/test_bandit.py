"""Tests for the UCB backend-selection bandit."""

import pytest

from polyharness.proposer.bandit import BackendBandit


def test_cold_start_tries_each_backend_in_order():
    b = BackendBandit(["api", "local", "codex"])
    # With nothing pulled yet, selection walks the backends in order.
    assert b.select() == "api"
    b.update("api", 1.0)
    assert b.select() == "local"
    b.update("local", 1.0)
    assert b.select() == "codex"


def test_converges_to_better_backend():
    b = BackendBandit(["good", "bad"], c=0.5)
    # Cold start: one pull each.
    b.update(b.select(), 1.0)  # good
    b.update(b.select(), 0.0)  # bad
    # Now reward "good" highly and "bad" poorly over many rounds.
    picks = {"good": 0, "bad": 0}
    for _ in range(50):
        choice = b.select()
        picks[choice] += 1
        b.update(choice, 1.0 if choice == "good" else 0.0)
    assert picks["good"] > picks["bad"]


def test_deterministic_tie_breaks_by_order():
    # Two identical arms → ties always resolve to the first backend.
    b1 = BackendBandit(["x", "y"])
    b2 = BackendBandit(["x", "y"])
    for _ in range(10):
        c1, c2 = b1.select(), b2.select()
        assert c1 == c2
        b1.update(c1, 0.5)
        b2.update(c2, 0.5)


def test_dedupe_preserves_order():
    b = BackendBandit(["api", "api", "local"])
    assert b.backends == ["api", "local"]


def test_empty_backends_raises():
    with pytest.raises(ValueError):
        BackendBandit([])


def test_update_unknown_backend_raises():
    b = BackendBandit(["api"])
    with pytest.raises(KeyError):
        b.update("nope", 1.0)


def test_stats_shape():
    b = BackendBandit(["api", "local"])
    b.update("api", 1.0)
    b.update("api", 0.0)
    stats = b.stats()
    assert stats["api"] == {"pulls": 2, "mean_reward": 0.5}
    assert stats["local"] == {"pulls": 0, "mean_reward": 0.0}
    assert b.total_pulls == 2
