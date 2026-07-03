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
            # Canonical UCB1: mean + c·sqrt(ln n / nᵢ) with c = √2 by default.
            # (An extra factor of 2 inside the sqrt used to double-count the
            # exploration constant, over-exploring on small budgets.)
            return arm.mean + self.c * math.sqrt(math.log(total) / arm.count)

        # max() returns the first item on ties → deterministic by order.
        return max(self.backends, key=ucb)

    def update(self, backend: str, reward: float) -> None:
        """Record a reward in ``[0, 1]`` for *backend*."""
        if backend not in self._arms:
            raise KeyError(f"Unknown backend for bandit update: {backend}")
        if not 0.0 <= reward <= 1.0:
            raise ValueError(f"Bandit reward must be in [0, 1], got {reward!r}")
        arm = self._arms[backend]
        arm.count += 1
        arm.total_reward += reward

    def stats(self) -> dict[str, dict[str, float | int]]:
        """Return per-backend pull counts and mean rewards (for reporting)."""
        return {
            b: {"pulls": arm.count, "mean_reward": round(arm.mean, 4)}
            for b, arm in self._arms.items()
        }

    # -- persistence (so resume doesn't reset learned preferences) ----------

    def to_dict(self) -> dict:
        """Full-precision state for persistence across resume."""
        return {
            "c": self.c,
            "arms": {
                b: {"count": arm.count, "total_reward": arm.total_reward}
                for b, arm in self._arms.items()
            },
        }

    def load_dict(self, state: dict) -> None:
        """Restore state saved by :meth:`to_dict`.

        Arms present in the state but no longer configured are ignored;
        newly configured backends keep their cold-start status.
        """
        for b, arm_state in (state.get("arms") or {}).items():
            if b in self._arms:
                self._arms[b] = _Arm(
                    count=int(arm_state.get("count", 0)),
                    total_reward=float(arm_state.get("total_reward", 0.0)),
                )
