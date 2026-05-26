"""Proposer — the agent that reads workspace history and writes new harness candidates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

# Shared improvement directives appended to every Proposer's prompt/instructions.
# Distilled from the Stanford Meta-Harness reference Skill (MIT) — re-authored,
# not copied — to push proposers toward high-value, generalizable changes.
PROPOSER_PRINCIPLES = """\
## Improvement principles
- Change a real mechanism, not just constants. If your edit only tweaks thresholds,
  weights, or wording versus the parent, it is a low-value parameter variant —
  instead change the actual logic, strategy, or data structure.
- Stay general; do not overfit. Never hardcode answers or task-specific knowledge to
  inflate the score. The harness must generalize beyond the eval cases you can see.
- Ground the change in evidence. Before finalizing, point to the specific failures or
  regressions in the traces that your change targets, and reason through why it fixes them.
- State a falsifiable hypothesis. In your summary, say what you expect to improve and
  why, so the next iteration can tell whether it held.
"""


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
