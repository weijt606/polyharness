"""Proposer — the agent that reads workspace history and writes new harness candidates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseProposer(ABC):
    """Abstract Proposer interface.

    A Proposer reads the workspace (history, scores, traces) and produces
    a new candidate harness in `candidates/iter_{iteration}/`.
    """

    @abstractmethod
    def propose(self, workspace_root: Path, candidate_dir: Path, iteration: int, parent: int | None) -> dict:
        """Generate a new harness candidate.

        Args:
            workspace_root: Root of the optimization workspace.
            candidate_dir: Target directory for the new candidate (already seeded from parent).
            iteration: Current iteration number.
            parent: Parent iteration number, or None for first iteration.

        Returns:
            Metadata dict with at least 'changes_summary' key.
        """
        ...
