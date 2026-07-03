"""Orchestrator — the Meta-Harness search loop coordinator."""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from polyharness.config import PolyHarnessConfig
from polyharness.evaluator import BaseEvaluator, EvalResult, create_evaluator
from polyharness.integrity import (
    HoldoutVault,
    IntegrityError,
    IntegrityGuard,
    sha256_file,
)
from polyharness.proposer import BaseProposer, create_proposer
from polyharness.proposer.bandit import BackendBandit
from polyharness.search_log import SearchLog
from polyharness.workspace import Workspace

console = Console()


@dataclass
class SearchResult:
    """Final result of a search run."""

    best_iteration: int
    best_score: float
    total_iterations: int
    test_score: float | None = None  # held-out test score (eval_split only)


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
        proposers: dict[str, BaseProposer] | None = None,
    ):
        self.workspace = workspace
        self.config = config
        self.evaluator = evaluator or create_evaluator(config.evaluator, cwd=workspace.root)
        self.search_log = SearchLog(workspace.search_log_path)

        # Cache of backend-name → proposer. Pre-seeded ones (e.g. from tests)
        # are used as-is; others are created lazily on first use.
        self._proposer_cache: dict[str, BaseProposer] = dict(proposers or {})

        # Ensemble (bandit) mode is opt-in and only active when the caller did
        # not inject a single fixed proposer. An explicit `proposer=` always
        # wins, keeping existing behavior and tests unchanged.
        ensemble = config.proposer.ensemble
        if proposer is None and ensemble:
            self.bandit: BackendBandit | None = BackendBandit(
                list(ensemble), c=config.proposer.bandit_c
            )
            self.proposer: BaseProposer | None = None  # chosen per iteration
        else:
            self.bandit = None
            self.proposer = (
                proposer
                or self._proposer_cache.get(config.proposer.backend)
                or create_proposer(config.proposer)
            )

        # Set up by run(); None until then so unit tests can poke internals.
        self._guard: IntegrityGuard | None = None
        self._vault: HoldoutVault | None = None
        self._base_entry_hash: str | None = None
        self._root_entry_exists: bool = False

    def run(self, resume: bool = False) -> SearchResult:
        """Execute the full search loop (holding the workspace lock)."""
        with self.workspace.exclusive_lock():
            cfg = self.config.evaluator
            # Holdout isolation: keep test task files out of the searchable
            # tree while the proposer works; restored for the final scoring.
            if cfg.eval_split and cfg.test_tasks:
                self._vault = HoldoutVault(self.workspace.root, cfg.test_tasks)
                self._vault.stash()
            self._init_integrity_guard()
            try:
                return self._run(resume=resume)
            finally:
                if self._vault is not None:
                    self._vault.restore()

    def _init_integrity_guard(self) -> None:
        """Hash the reward-defining files so mid-run tampering aborts the run."""
        cfg = self.config.evaluator
        guarded: list[str] = []
        root_entry = self.workspace.root / cfg.entry
        base_entry = self.workspace.base_harness_dir / cfg.entry
        self._root_entry_exists = root_entry.is_file()
        if self._root_entry_exists:
            guarded.append(cfg.entry)
        if base_entry.is_file():
            self._base_entry_hash = sha256_file(base_entry)
            guarded.append(f"base_harness/{cfg.entry}")
        guarded.extend(self._search_tasks())
        self._guard = IntegrityGuard(self.workspace.root, guarded)

    def _verify_integrity(self, cand_dir=None) -> None:
        """Fail fast if the evaluate script or task files were modified."""
        if self._guard is None:
            return
        self._guard.verify_or_raise()
        # When the evaluate script lives inside candidates (no workspace-root
        # copy), each candidate's own copy is what actually runs — verify it
        # against the base harness version.
        if (
            cand_dir is not None
            and not self._root_entry_exists
            and self._base_entry_hash is not None
        ):
            cand_entry = cand_dir / self.config.evaluator.entry
            if cand_entry.is_file() and sha256_file(cand_entry) != self._base_entry_hash:
                raise IntegrityError(
                    f"{cand_entry} differs from the base evaluate script — "
                    "a candidate must not modify its own scorer. Aborting."
                )

    def _run(self, resume: bool = False) -> SearchResult:
        max_iter = self.config.search.max_iterations

        # Reproducibility: seed RNG so tournament/pareto/novelty are repeatable.
        if self.config.search.seed is not None:
            random.seed(self.config.search.seed)

        console.rule("[bold blue]PolyHarness Optimization Loop")
        console.print(f"Max iterations: {max_iter}")
        console.print(f"Early stop patience: {self.config.search.early_stop_patience}")
        if self.bandit is not None:
            console.print(
                f"Proposer ensemble: {', '.join(self.bandit.backends)} (UCB bandit)"
            )
        else:
            console.print(f"Proposer backend: {self.config.proposer.backend}")
        _ecfg = self.config.evaluator
        if _ecfg.eval_split and _ecfg.val_tasks and _ecfg.test_tasks:
            console.print(
                f"Eval split: evolve on {len(_ecfg.val_tasks)} val task(s), "
                f"held-out {len(_ecfg.test_tasks)} test task(s)"
            )
        console.print()

        # Determine starting point (resume or fresh)
        start_iter = 1
        best_score = 0.0
        best_iteration = 0
        patience_counter = 0

        if resume and len(self.search_log) > 0:
            # Restore state from existing search log
            entries = self.search_log.entries
            best_score = self.search_log.best_score
            best_iteration = self.search_log.best_iteration
            start_iter = max(e.iteration for e in entries) + 1

            # Recalculate patience_counter from tail of entries: every logged
            # entry after the record-setting iteration incremented patience at
            # run time (ties with the best count too — they don't reset it).
            patience_counter = 0
            for e in reversed(entries):
                if e.iteration == 0 or e.iteration == best_iteration:
                    break
                patience_counter += 1

            console.print(
                f"[yellow]Resuming from iter_{start_iter - 1} "
                f"(best={best_score:.4f} at iter_{best_iteration}, "
                f"patience={patience_counter}/{self.config.search.early_stop_patience})[/yellow]"
            )
            console.print()
        else:
            # Step 0: Evaluate base harness
            console.print("[bold]Step 0:[/bold] Evaluating base harness...")
            try:
                base_result = self._evaluate_iteration(0, is_base=True).overall_score
            except FileNotFoundError as e:
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Your workspace is missing an evaluate script. "
                    "Re-initialize with:\n"
                    "  ph init --task-dir ./your_tasks/   (if it contains evaluate.py)\n"
                    "  ph init --eval-script ./evaluate.py  (to specify one directly)\n"
                    "\nOr copy an evaluate.py into the workspace root."
                )
                raise SystemExit(1)
            best_score = base_result
            best_iteration = 0

            self._print_iteration(0, base_result, best_score, None)

        if max_iter == 0:
            console.print("\n[yellow]Dry run — base evaluation only.[/yellow]")
            return SearchResult(
                best_iteration=0,
                best_score=best_score,
                total_iterations=0,
            )

        remaining = max_iter - (start_iter - 1)
        if remaining <= 0:
            console.print("[yellow]All iterations already completed.[/yellow]")
            result = SearchResult(
                best_iteration=best_iteration,
                best_score=best_score,
                total_iterations=len(self.search_log) - 1,
                test_score=self._evaluate_holdout(best_iteration),
            )
            self._print_summary(result)
            return result

        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("best={task.fields[best]:.4f}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Searching", total=remaining, best=best_score)

            for i in range(start_iter, max_iter + 1):
                progress.update(task, description=f"iter_{i}")

                backend: str | None = None
                try:
                    # Step 1: Select parent
                    parent = self._select_parent()

                    # Step 1.5: Select which backend proposes this iteration
                    # (bandit) or fall back to the single fixed proposer.
                    backend, proposer = self._select_proposer()

                    # Steps 2–3: Propose a candidate, optionally rejecting
                    # near-duplicates (novelty filter).
                    cand_dir, metadata, accepted = self._propose_with_novelty(
                        i, parent, proposer
                    )

                    # If the candidate is a near-duplicate even after retries,
                    # skip its (potentially expensive) evaluation entirely.
                    if not accepted:
                        console.print(
                            f"\n[yellow]iter_{i}: skipped — near-duplicate of an "
                            f"earlier candidate (saved evaluation budget)[/yellow]"
                        )
                        # Drop the dangling candidate dir so its copied-from-parent
                        # score.json doesn't pollute the leaderboard.
                        shutil.rmtree(cand_dir, ignore_errors=True)
                        self._reward_backend(backend, 0.0)  # duplicate = no value
                        patience_counter += 1
                        progress.update(task, advance=1)
                        if patience_counter >= self.config.search.early_stop_patience:
                            break
                        continue

                    # Step 4: Evaluate
                    eval_result = self._evaluate_iteration(i, parent=parent)
                    score = eval_result.overall_score
                except IntegrityError:
                    # Tampered scorer/tasks: scores are no longer trustworthy.
                    # Abort the whole run instead of logging a fake iteration.
                    shutil.rmtree(self.workspace.candidate_path(i), ignore_errors=True)
                    raise
                except Exception as exc:
                    console.print(f"\n[red]iter_{i} failed: {exc}[/red]")
                    # Remove the half-built candidate dir: it still carries the
                    # parent's copied files and would otherwise be mistaken for
                    # a real candidate (and pollute future novelty checks).
                    shutil.rmtree(self.workspace.candidate_path(i), ignore_errors=True)
                    self._reward_backend(backend, 0.0)  # failure = no value
                    patience_counter += 1
                    progress.update(task, advance=1)
                    if patience_counter >= self.config.search.early_stop_patience:
                        break
                    continue

                # Record which backend produced this candidate (observability).
                if backend is not None:
                    metadata = {**metadata, "proposer_backend": backend}
                if eval_result.gated:
                    metadata = {**metadata, "cascade_gated": True}

                # Step 5: Store results
                log_entry = self.search_log.entries[-1]
                self.workspace.store_iteration(
                    iteration=i,
                    score=log_entry.score,
                    task_scores=log_entry.task_scores,
                    parent=parent,
                    metadata=metadata,
                )

                # Reward the backend when its candidate improved over its parent.
                self._reward_backend(
                    backend, 1.0 if score > self._parent_score(parent) else 0.0
                )

                # Step 6: Update best & check early stop
                if score > best_score:
                    best_score = score
                    best_iteration = i
                    patience_counter = 0
                else:
                    patience_counter += 1

                progress.update(task, advance=1, best=best_score)

                if patience_counter >= self.config.search.early_stop_patience:
                    break

        # Print iteration summary after progress bar completes
        console.print()
        prev_best: float | None = None
        for entry in self.search_log.entries:
            if entry.iteration > 0:
                # Delta compares against the best BEFORE this entry — an
                # entry's own best_so_far already includes itself, which made
                # delta permanently non-positive.
                self._print_iteration(
                    entry.iteration,
                    entry.score,
                    prev_best if prev_best is not None else entry.score,
                    entry.parent,
                )
            prev_best = entry.best_so_far

        if patience_counter >= self.config.search.early_stop_patience:
            console.print("\n[yellow]Early stopping triggered.[/yellow]")

        # Final summary (+ held-out test eval of the best candidate, if enabled)
        test_score = self._evaluate_holdout(best_iteration)
        result = SearchResult(
            best_iteration=best_iteration,
            best_score=best_score,
            total_iterations=len(self.search_log) - 1,
            test_score=test_score,
        )
        self._print_summary(result)
        return result

    def _evaluate_iteration(
        self, iteration: int, is_base: bool = False, parent: int | None = None
    ) -> EvalResult:
        """Evaluate a candidate and log results.

        `parent` is the actual parent chosen by the selection strategy — it is
        recorded verbatim (logging best_iteration here instead used to corrupt
        the lineage under tournament/pareto selection).
        """
        if is_base:
            # Evaluate the iter_0 copy, not base_harness/ itself, so traces
            # land in candidates/iter_0/traces/ where the Proposer is told to
            # look — and base_harness/ stays pristine.
            cand_dir = self.workspace.prepare_candidate(0, parent=None)
        else:
            cand_dir = self.workspace.candidate_path(iteration)
            self._verify_integrity(cand_dir)

        # Base harness is always scored in full; candidates may use cascade.
        eval_result = self._run_eval(cand_dir, allow_cascade=not is_base)

        self.search_log.append(
            iteration=iteration,
            parent=None if is_base else parent,
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

        return eval_result

    def _search_tasks(self) -> list[str]:
        """Tasks used during the search loop.

        With ``eval_split`` on, the loop evolves against ``val_tasks`` (held-out
        ``test_tasks`` are only touched once at the end). Otherwise the regular
        ``tasks`` list is used.
        """
        cfg = self.config.evaluator
        if cfg.eval_split and cfg.val_tasks:
            return cfg.val_tasks
        return cfg.tasks

    def _run_eval(self, cand_dir, *, allow_cascade: bool) -> EvalResult:
        """Evaluate a candidate, applying cascade when enabled and applicable."""
        tasks = self._search_tasks()
        if allow_cascade and self.config.evaluator.cascade and len(tasks) >= 2:
            return self._evaluate_with_cascade(cand_dir, tasks)
        return self.evaluator.evaluate(candidate_dir=cand_dir, tasks=tasks)

    def _evaluate_holdout(self, best_iteration: int) -> float | None:
        """Score the best candidate once on the held-out ``test_tasks``.

        Returns the overall test score (or ``None`` when split is off / unavailable).
        The result never drives selection — it's an honest, post-hoc number. Stored
        in ``summary/holdout_test.json``.
        """
        cfg = self.config.evaluator
        if not cfg.eval_split or not cfg.test_tasks:
            return None
        cand = self.workspace.candidate_path(best_iteration)
        if not cand.exists():
            return None

        # Bring the test tasks back from the vault and confirm neither they
        # nor the evaluate script changed during the search.
        if self._vault is not None:
            self._vault.restore()
            self._vault.verify_restored()
        self._verify_integrity(cand)

        console.print(
            f"\n[bold]Held-out test:[/bold] scoring iter_{best_iteration} on "
            f"{len(cfg.test_tasks)} test task(s) (not used for selection)..."
        )
        res = self.evaluator.evaluate(candidate_dir=cand, tasks=cfg.test_tasks)

        self.workspace.summary_dir.mkdir(exist_ok=True)
        (self.workspace.summary_dir / "holdout_test.json").write_text(
            json.dumps(
                {
                    "iteration": best_iteration,
                    "test_overall_score": res.overall_score,
                    "test_task_scores": res.task_scores,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        return res.overall_score

    def _evaluate_with_cascade(self, cand_dir, tasks: list[str]) -> EvalResult:
        """Staged evaluation: cheap subset first, full set only if it clears the gate.

        Splits *tasks* into a stage-1 subset and the rest. A candidate whose
        stage-1 mean falls below ``cascade_threshold`` is rejected early without
        running stage 2, saving evaluation budget on weak candidates
        (AlphaEvolve/OpenEvolve-style cascade). Stage-1 tasks are never
        re-evaluated, so the result is deterministic.
        """
        k = self.config.evaluator.cascade_stage1
        if k <= 0:
            k = max(1, (len(tasks) + 2) // 3)  # ~1/3 of tasks, rounded up
        k = min(k, len(tasks) - 1)  # always leave at least one task for stage 2

        stage1, stage2 = tasks[:k], tasks[k:]
        r1 = self.evaluator.evaluate(candidate_dir=cand_dir, tasks=stage1)

        threshold = self.config.evaluator.cascade_threshold
        if r1.overall_score < threshold:
            console.print(
                f"[dim]  cascade: gated at stage 1 "
                f"({r1.overall_score:.2f} < {threshold:.2f}) — "
                f"skipped {len(stage2)} task(s)[/dim]"
            )
            # Score over the FULL denominator (unrun stage-2 tasks count as 0)
            # so a gated partial result can never outrank fully-evaluated
            # candidates in best/leaderboard comparisons.
            penalized = (r1.overall_score * len(stage1)) / len(tasks)
            return EvalResult(
                overall_score=penalized,
                task_scores=r1.task_scores,
                traces=r1.traces,
                gated=True,
            )

        r2 = self.evaluator.evaluate(candidate_dir=cand_dir, tasks=stage2)
        task_scores = {**r1.task_scores, **r2.task_scores}
        traces = {**r1.traces, **r2.traces}
        overall = (
            sum(task_scores.values()) / len(task_scores) if task_scores else 0.0
        )
        return EvalResult(overall_score=overall, task_scores=task_scores, traces=traces)

    def _select_parent(self) -> int:
        """Select parent candidate based on strategy."""
        strategy = self.config.search.parent_selection
        if strategy == "best":
            return self.search_log.best_iteration
        elif strategy == "tournament":
            return self._tournament_select()
        elif strategy == "pareto":
            return self._pareto_select()
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

    def _pareto_select(self) -> int:
        """GEPA-style Pareto-frontier parent selection.

        Rather than always branching from the single best *overall* candidate,
        build the set of candidates that achieve the top score on at least one
        individual task ("per-task winners"), then sample one of them weighted
        by how many tasks it wins.  This keeps specialists that are strong on a
        subset of tasks alive as stepping stones, avoiding premature
        convergence (Pareto-based selection, GEPA — arXiv:2507.19457).

        Falls back to ``best`` when per-task scores are unavailable.
        """
        win_counts = self.search_log.pareto_win_counts()
        if not win_counts:
            return self.search_log.best_iteration

        iterations = list(win_counts.keys())
        weights = [win_counts[i] for i in iterations]
        return random.choices(iterations, weights=weights, k=1)[0]

    def _select_proposer(self) -> tuple[str | None, BaseProposer]:
        """Pick the proposer for this iteration.

        Returns ``(backend_name, proposer)``. In single-backend mode the name
        is ``None`` and the fixed proposer is returned. In ensemble mode the
        UCB bandit chooses a backend and its (lazily created) proposer.
        """
        if self.bandit is None:
            assert self.proposer is not None
            return None, self.proposer
        backend = self.bandit.select()
        return backend, self._get_proposer(backend)

    def _get_proposer(self, backend: str) -> BaseProposer:
        """Return (creating + caching on first use) the proposer for *backend*."""
        if backend not in self._proposer_cache:
            sub_config = self.config.proposer.model_copy(update={"backend": backend})
            self._proposer_cache[backend] = create_proposer(sub_config)
        return self._proposer_cache[backend]

    def _reward_backend(self, backend: str | None, reward: float) -> None:
        """Feed a reward to the bandit (no-op in single-backend mode)."""
        if self.bandit is not None and backend is not None:
            self.bandit.update(backend, reward)

    def _parent_score(self, parent: int | None) -> float:
        """Score of the parent iteration (0.0 if unknown)."""
        if parent is None:
            return 0.0
        for entry in self.search_log.entries:
            if entry.iteration == parent:
                return entry.score
        return 0.0

    def _propose_with_novelty(self, iteration: int, parent: int, proposer: BaseProposer):
        """Propose a candidate, optionally rejecting near-duplicates.

        Returns ``(candidate_dir, metadata, accepted)``.  When the novelty
        filter is enabled and the proposer keeps producing a candidate that is
        too similar to an earlier one, regenerate up to ``novelty_max_retries``
        times; if still a near-duplicate, return ``accepted=False`` so the
        caller can skip evaluation and save budget (ShinkaEvolve-style code
        novelty rejection — arXiv:2509.19349).
        """
        cand_dir, metadata = self._propose_candidate(iteration, parent, proposer)

        if not self.config.search.novelty_filter:
            return cand_dir, metadata, True

        threshold = self.config.search.novelty_threshold
        max_retries = self.config.search.novelty_max_retries

        for attempt in range(max_retries + 1):
            similarity = self._max_similarity(iteration, cand_dir)
            if similarity < threshold:
                return cand_dir, metadata, True
            if attempt < max_retries:
                console.print(
                    f"[dim]iter_{iteration}: candidate {similarity:.2f} similar to an "
                    f"existing one — regenerating ({attempt + 1}/{max_retries})[/dim]"
                )
                cand_dir, metadata = self._propose_candidate(iteration, parent, proposer)

        return cand_dir, metadata, False

    def _propose_candidate(self, iteration: int, parent: int, proposer: BaseProposer):
        """Prepare a candidate dir, run the proposer, and verify output.

        Returns ``(candidate_dir, metadata)``.  Raises ``FileNotFoundError``
        when the proposer fails to produce ``harness.py``.
        """
        cand_dir = self.workspace.prepare_candidate(iteration, parent)
        metadata = proposer.propose(
            workspace_root=self.workspace.root,
            candidate_dir=cand_dir,
            iteration=iteration,
            parent=parent,
        )
        if not (cand_dir / "harness.py").exists():
            raise FileNotFoundError(
                f"Proposer did not generate harness.py in iter_{iteration}"
            )
        return cand_dir, metadata

    def _max_similarity(self, iteration: int, cand_dir) -> float:
        """Max text similarity of *cand_dir* against all earlier candidates.

        Uses :class:`difflib.SequenceMatcher` (stdlib, no extra deps) on the
        concatenated editable harness files. Returns a ratio in ``[0, 1]``.
        """
        from difflib import SequenceMatcher

        new_text = self._candidate_text(cand_dir)
        if not new_text:
            return 0.0

        best = 0.0
        for entry in self.search_log.entries:
            if entry.iteration == iteration:
                continue
            other_dir = self.workspace.candidate_path(entry.iteration)
            if not other_dir.exists():
                continue
            other_text = self._candidate_text(other_dir)
            if not other_text:
                continue
            ratio = SequenceMatcher(None, new_text, other_text).ratio()
            if ratio > best:
                best = ratio
        return best

    def _candidate_text(self, cand_dir) -> str:
        """Concatenate a candidate's editable harness files into one blob."""
        parts: list[str] = []
        for fname in self.config.harness.editable_files:
            f = cand_dir / fname
            if f.is_file():
                parts.append(f.read_text())
        if not parts:
            entry = cand_dir / self.config.harness.entry
            if entry.is_file():
                parts.append(entry.read_text())
        return "\n".join(parts)

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
        score_label = "Best score (val)" if result.test_score is not None else "Best score"
        table.add_row(score_label, f"{result.best_score:.4f}")
        if result.test_score is not None:
            table.add_row("Held-out test score", f"{result.test_score:.4f}")
        table.add_row("Total iterations", str(result.total_iterations))
        console.print(table)

        # Ensemble bandit breakdown: which backend earned its picks.
        if self.bandit is not None and self.bandit.total_pulls > 0:
            bandit_table = Table(title="Proposer ensemble (UCB bandit)")
            bandit_table.add_column("Backend")
            bandit_table.add_column("Picks", justify="right")
            bandit_table.add_column("Improve rate", justify="right")
            for backend, s in self.bandit.stats().items():
                bandit_table.add_row(
                    backend, str(s["pulls"]), f"{s['mean_reward']:.2f}"
                )
            console.print(bandit_table)

        console.print(
            "\nRun [bold]ph best[/bold] to see details, or [bold]ph apply[/bold] to apply the result."
        )
