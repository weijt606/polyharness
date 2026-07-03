"""Proposer — the agent that reads workspace history and writes new harness candidates."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

# Filename the orchestrator uses to hand rejection/failure feedback to the
# next proposal attempt (reflective retry). Written into the candidate dir.
FEEDBACK_FILENAME = "PROPOSER_FEEDBACK.md"

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


def build_proposer_context(
    workspace_root: Path,
    candidate_dir: Path,
    iteration: int,
    parent: int | None,
) -> str:
    """Shared prompt body used by every proposer backend.

    Keeping this in one place stops the three prompts (CLI / Anthropic /
    OpenAI-compatible) from drifting apart — previously the OpenAI backend,
    serving the weakest models, had the thinnest instructions.
    """
    parent_label = f"iter_{parent}" if parent is not None else "base_harness (first iteration)"
    cand_rel = candidate_dir.relative_to(workspace_root)

    return f"""\
## Workspace Layout
- workspace root: {workspace_root}
- candidates/iter_0/, iter_1/, ... — previous candidates, each with:
  - harness code files (the code you can improve)
  - score.json — evaluation results
  - traces/ — execution traces (stdout, stderr, metrics)
- base_harness/ — the starting harness code
- search_log.jsonl — chronological log of all iterations and scores
- summary/LESSONS.md — digest of what already worked and what already failed
- config.yaml — search configuration
{_leaderboard_section(workspace_root)}
## Current Task
- Iteration: {iteration}
- Parent candidate: {parent_label}
- Your candidate directory: {cand_rel}/

## Instructions
1. If {cand_rel}/{FEEDBACK_FILENAME} exists, read it FIRST — it explains why
   your previous attempt was rejected and what to do differently.
2. Read summary/LESSONS.md for a digest of the search so far, then dig into
   the parent candidate's score.json and traces/ for specifics.
3. Identify one concrete improvement opportunity from failure patterns.
4. Modify harness code files ONLY inside your candidate directory ({cand_rel}/).
5. Afterwards, summarize what you changed and the hypothesis behind it.

## Rules
- Do NOT modify files outside {cand_rel}/.
- Do NOT modify score.json, metadata.json, search_log.jsonl, or evaluate
  scripts — the evaluator owns them, and any change is detected and aborts
  the whole run.
- Aim for improvements that are testable and measurable.

{PROPOSER_PRINCIPLES}"""


def _leaderboard_section(workspace_root: Path) -> str:
    """Structured leaderboard extract: numbers only.

    Deliberately NOT the raw leaderboard.json — that file embeds previous
    agents' free text, which would let one iteration inject instructions
    into the next one's prompt.
    """
    lb_path = workspace_root / "summary" / "leaderboard.json"
    if not lb_path.exists():
        return ""
    try:
        entries = json.loads(lb_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return ""
    lines = []
    for e in entries[:10]:
        try:
            lines.append(f"- iter_{int(e['iteration'])}: {float(e['overall_score']):.4f}")
        except (KeyError, TypeError, ValueError):
            continue
    if not lines:
        return ""
    return "\n## Current Leaderboard (top scores)\n" + "\n".join(lines) + "\n"


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
