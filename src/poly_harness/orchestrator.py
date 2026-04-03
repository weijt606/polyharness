"""Orchestrator — the Meta-Harness search loop coordinator."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from poly_harness.config import PolyHarnessConfig
from poly_harness.evaluator import BaseEvaluator, create_evaluator
from poly_harness.proposer import BaseProposer, create_proposer
from poly_harness.search_log import SearchLog
from poly_harness.workspace import Workspace

console = Console()


@dataclass
class SearchResult:
    """Final result of a search run."""

    best_iteration: int
    best_score: float
    total_iterations: int


class Orchestrator:
    """Meta-Harness search loop orchestrator.

    Coordinates proposer → evaluate → store cycle.
    """

    def __init__(
        self,
        workspace: Workspace,
        config: PolyHarnessConfig,
        proposer: BaseProposer | None = None,
        evaluator: BaseEvaluator | None = None,
    ):
        self.workspace = workspace
        self.config = config
        self.proposer = proposer or create_proposer(config.proposer)
        self.evaluator = evaluator or create_evaluator(config.evaluator, cwd=workspace.root)
        self.search_log = SearchLog(workspace.search_log_path)

    def run(self) -> SearchResult:
        """Execute the full search loop."""

        console.rule("[bold blue]PolyHarness Optimization Loop")
        console.print(f"Max iterations: {self.config.search.max_iterations}")
        console.print(f"Early stop patience: {self.config.search.early_stop_patience}")
        console.print(f"Proposer backend: {self.config.proposer.backend}")
        console.print()

        # Step 0: Evaluate base harness
        console.print("[bold]Step 0:[/bold] Evaluating base harness...")
        base_result = self._evaluate_iteration(0, is_base=True)
        best_score = base_result
        best_iteration = 0
        patience_counter = 0

        self._print_iteration(0, base_result, best_score, None)

        for i in range(1, self.config.search.max_iterations + 1):
            console.rule(f"[bold]Iteration {i}")

            # Step 1: Select parent
            parent = self._select_parent()

            # Step 2: Prepare candidate directory (copy from parent)
            console.print(f"  Proposer: generating candidate from iter_{parent}...")
            cand_dir = self.workspace.prepare_candidate(i, parent)

            # Step 3: Proposer generates new candidate
            metadata = self.proposer.propose(
                workspace_root=self.workspace.root,
                candidate_dir=cand_dir,
                iteration=i,
                parent=parent,
            )

            # Step 4: Evaluate
            console.print("  Evaluator: running evaluation...")
            score = self._evaluate_iteration(i)

            # Step 5: Store results
            log_entry = self.search_log.entries[-1]  # just appended in _evaluate_iteration
            self.workspace.store_iteration(
                iteration=i,
                score=log_entry.score,
                task_scores=log_entry.task_scores,
                parent=parent,
                metadata=metadata,
            )

            self._print_iteration(i, score, best_score, parent)

            # Step 6: Update best & check early stop
            if score > best_score:
                best_score = score
                best_iteration = i
                patience_counter = 0
                console.print(f"  [bold green]New best! Score: {score:.4f}[/bold green]")
            else:
                patience_counter += 1
                console.print(f"  No improvement. Patience: {patience_counter}/{self.config.search.early_stop_patience}")

            if patience_counter >= self.config.search.early_stop_patience:
                console.print("\n[yellow]Early stopping triggered.[/yellow]")
                break

        # Final summary
        result = SearchResult(
            best_iteration=best_iteration,
            best_score=best_score,
            total_iterations=len(self.search_log) - 1,
        )
        self._print_summary(result)
        return result

    def _evaluate_iteration(self, iteration: int, is_base: bool = False) -> float:
        """Evaluate a candidate and log results."""
        if is_base:
            cand_dir = self.workspace.base_harness_dir
            # Also store as iter_0
            iter_dir = self.workspace.candidate_path(0)
            if not iter_dir.exists():
                self.workspace.prepare_candidate(0, parent=None)
        else:
            cand_dir = self.workspace.candidate_path(iteration)

        eval_result = self.evaluator.evaluate(
            candidate_dir=cand_dir,
            tasks=self.config.evaluator.tasks,
        )

        parent = None if is_base else self.search_log.best_iteration
        self.search_log.append(
            iteration=iteration,
            parent=parent,
            score=eval_result.overall_score,
            task_scores=eval_result.task_scores,
        )

        if is_base:
            self.workspace.store_iteration(
                iteration=0,
                score=eval_result.overall_score,
                task_scores=eval_result.task_scores,
                parent=None,
                metadata={"source": "base_harness"},
            )

        return eval_result.overall_score

    def _select_parent(self) -> int:
        """Select parent candidate based on strategy."""
        strategy = self.config.search.parent_selection
        if strategy == "best":
            return self.search_log.best_iteration
        elif strategy == "tournament":
            return self._tournament_select()
        else:  # "all" — proposer decides, so we pass best as default parent
            return self.search_log.best_iteration

    def _tournament_select(self, k: int = 3) -> int:
        """Randomized tournament selection.

        Randomly sample *k* entries from the search log and return the
        iteration with the highest score.  This adds diversity while still
        biasing towards stronger candidates — matching the "candidate
        selection strategy" requirement from the product doc.
        """
        entries = self.search_log.entries
        if len(entries) <= k:
            contestants = entries
        else:
            contestants = random.sample(entries, k)
        return max(contestants, key=lambda e: e.score).iteration

    def _print_iteration(self, iteration: int, score: float, best_so_far: float, parent: int | None) -> None:
        parent_str = f"iter_{parent}" if parent is not None else "base"
        delta = score - best_so_far if iteration > 0 else 0
        delta_str = f"{delta:+.4f}" if iteration > 0 else "—"
        console.print(
            f"  iter_{iteration}: score={score:.4f}  best={max(score, best_so_far):.4f}  "
            f"delta={delta_str}  parent={parent_str}"
        )

    def _print_summary(self, result: SearchResult) -> None:
        console.print()
        console.rule("[bold green]Search Complete")
        table = Table(show_header=False)
        table.add_row("Best iteration", f"iter_{result.best_iteration}")
        table.add_row("Best score", f"{result.best_score:.4f}")
        table.add_row("Total iterations", str(result.total_iterations))
        console.print(table)
        console.print(
            f"\nRun [bold]ph best[/bold] to see details, or [bold]ph apply[/bold] to apply the result."
        )
