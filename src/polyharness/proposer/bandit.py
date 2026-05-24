"""UCB1 bandit for adaptive multi-backend proposer selection.

When several proposer backends are available, we don't know up front which one
writes the best harness changes for a given task. Instead of committing to one,
the orchestrator can treat backend choice as a multi-armed bandit: each
iteration it picks the backend with the highest UCB score, observes whether the
produced candidate improved, and updates its estimate.

Design notes (aligned with project principles):
- **Deterministic.** UCB1 is fully deterministic given the reward sequence;
  ties break by configured backend order. No RNG, so runs are reproducible.
- **No new dependencies.** Pure stdlib (``math``).
- **No new attack surface.** It only chooses among already-configured backends;
  it never constructs commands or executes anything itself.

Inspired by ShinkaEvolve's adaptive LLM-ensemble selection (arXiv:2509.19349).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class _Arm:
    count: int = 0
    total_reward: float = 0.0

    @property
    def mean(self) -> float:
        return self.total_reward / self.count if self.count else 0.0


class BackendBandit:
    """UCB1 multi-armed bandit over a fixed set of backend names."""

    def __init__(self, backends: list[str], c: float = 1.41421356):
        if not backends:
            raise ValueError("BackendBandit requires at least one backend.")
        # Preserve order (used for deterministic tie-breaking) and dedupe.
        self.backends: list[str] = list(dict.fromkeys(backends))
        self.c = c
        self._arms: dict[str, _Arm] = {b: _Arm() for b in self.backends}

    @property
    def total_pulls(self) -> int:
        return sum(arm.count for arm in self._arms.values())

    def select(self) -> str:
        """Return the backend to use next.

        Every backend is tried once before UCB scoring kicks in. Ties resolve
        to the earliest backend in the configured order, keeping selection
        deterministic and reproducible.
        """
        # Cold start: try each unpulled backend in order first.
        for b in self.backends:
            if self._arms[b].count == 0:
                return b

        total = self.total_pulls

        def ucb(b: str) -> float:
            arm = self._arms[b]
            return arm.mean + self.c * math.sqrt(2 * math.log(total) / arm.count)

        # max() returns the first item on ties → deterministic by order.
        return max(self.backends, key=ucb)

    def update(self, backend: str, reward: float) -> None:
        """Record a reward in ``[0, 1]`` for *backend*."""
        if backend not in self._arms:
            raise KeyError(f"Unknown backend for bandit update: {backend}")
        arm = self._arms[backend]
        arm.count += 1
        arm.total_reward += reward

    def stats(self) -> dict[str, dict[str, float | int]]:
        """Return per-backend pull counts and mean rewards (for reporting)."""
        return {
            b: {"pulls": arm.count, "mean_reward": round(arm.mean, 4)}
            for b, arm in self._arms.items()
        }
