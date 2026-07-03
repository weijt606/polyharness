"""Evaluation integrity — tamper detection and holdout isolation.

The proposer is an arbitrary agent with write access to the workspace. Two
prompt-only rules ("don't edit evaluate.py", "don't overfit to the test set")
previously had no mechanical backing. This module provides it:

- `IntegrityGuard` hashes the evaluate script and every task file at run
  start and re-verifies before each evaluation. A tampered scorer or task
  file aborts the run instead of laundering fake scores into the log.
- `HoldoutVault` moves the held-out test task files out of the normal task
  tree (into `.ph_holdout/`) for the duration of the search, so the
  proposer's ordinary exploration never encounters them, and restores them
  (hash-verified) for the final holdout scoring. A manifest makes the move
  crash-recoverable.

CLI agents ultimately run with the user's filesystem permissions, so this is
tamper-*evidence* plus accident-prevention, not a jail — see the README's
threat-model note.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


class IntegrityError(RuntimeError):
    """The evaluation pipeline was modified mid-run."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class IntegrityGuard:
    """Snapshot + re-verify the files that define the reward function."""

    def __init__(self, workspace_root: Path, files: list[str | Path]):
        self.workspace_root = Path(workspace_root)
        self._hashes: dict[str, str | None] = {}
        for f in files:
            p = self._abs(f)
            key = str(f)
            self._hashes[key] = sha256_file(p) if p.is_file() else None

    def _abs(self, f: str | Path) -> Path:
        p = Path(f)
        return p if p.is_absolute() else self.workspace_root / p

    def verify(self) -> list[str]:
        """Return the list of guarded files whose content changed."""
        violations = []
        for key, expected in self._hashes.items():
            p = self._abs(key)
            actual = sha256_file(p) if p.is_file() else None
            if actual != expected:
                violations.append(key)
        return violations

    def verify_or_raise(self) -> None:
        violations = self.verify()
        if violations:
            raise IntegrityError(
                "Evaluation pipeline was modified during the run: "
                + ", ".join(violations)
                + ". Aborting — scores after this point would not be trustworthy. "
                "Restore the file(s) and re-run."
            )


class HoldoutVault:
    """Keeps held-out test task files outside the workspace during search."""

    VAULT_DIR = ".ph_holdout"
    MANIFEST = "manifest.json"

    def __init__(self, workspace_root: Path, test_tasks: list[str]):
        self.workspace_root = Path(workspace_root)
        self.test_tasks = list(test_tasks)
        self.vault = self.workspace_root / self.VAULT_DIR
        self._manifest_path = self.vault / self.MANIFEST
        self._hashes: dict[str, str] = {}

    # -- lifecycle -----------------------------------------------------------

    def stash(self) -> None:
        """Move test task files into the vault (recovering any stale stash first)."""
        self.recover()  # a previous crash may have left files stashed
        self.vault.mkdir(exist_ok=True)
        manifest: dict[str, str] = {}
        for i, task in enumerate(self.test_tasks):
            src = self._abs(task)
            if not src.is_file():
                continue
            self._hashes[task] = sha256_file(src)
            dest = self.vault / f"{i}_{src.name}"
            shutil.move(str(src), dest)
            manifest[task] = dest.name
        self._manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )

    def restore(self) -> None:
        """Move stashed files back to their original paths."""
        if not self._manifest_path.exists():
            return
        manifest = json.loads(self._manifest_path.read_text())
        for task, vault_name in manifest.items():
            src = self.vault / vault_name
            dest = self._abs(task)
            if src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), dest)
        shutil.rmtree(self.vault, ignore_errors=True)

    def recover(self) -> None:
        """Restore a stash left behind by a crashed previous run."""
        if self._manifest_path.exists():
            self.restore()

    # -- verification --------------------------------------------------------

    def verify_restored(self) -> None:
        """After restore, confirm test files match their pre-search hashes."""
        changed = []
        for task, expected in self._hashes.items():
            p = self._abs(task)
            actual = sha256_file(p) if p.is_file() else None
            if actual != expected:
                changed.append(task)
        if changed:
            raise IntegrityError(
                "Held-out test task(s) changed during the run: "
                + ", ".join(changed)
                + ". The holdout score would be meaningless. "
                "Restore the file(s) and re-run the holdout evaluation."
            )

    def _abs(self, f: str) -> Path:
        p = Path(f)
        return p if p.is_absolute() else self.workspace_root / p
