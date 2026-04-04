#!/usr/bin/env node

/**
 * ph — PolyHarness CLI wrapper for npm installations.
 *
 * This thin wrapper finds and invokes the Python `ph` CLI.
 * Resolution order:
 *   1. `ph` on PATH (pip-installed entry point)
 *   2. `python -m polyharness` (PYTHONPATH / editable install)
 *   3. Local .venv (auto-detect venv in cwd or parents)
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import process from "node:process";

const args = process.argv.slice(2);

/** Try running a command; return true on success. */
function tryExec(cmd, cmdArgs) {
  try {
    execFileSync(cmd, cmdArgs, { stdio: "inherit" });
    return true;
  } catch {
    return false;
  }
}

/** Walk up from cwd looking for .venv/bin/python. */
function findVenvPython() {
  let dir = process.cwd();
  const root = dirname(dir) === dir ? dir : "/";
  for (let i = 0; i < 10; i++) {
    const candidate = join(dir, ".venv", "bin", "python");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

// Strategy 1: `ph` on PATH
if (tryExec("ph", args)) process.exit(0);

// Strategy 2: system python -m polyharness
for (const py of ["python3", "python"]) {
  if (tryExec(py, ["-m", "polyharness", ...args])) process.exit(0);
}

// Strategy 3: auto-detect .venv
const venvPy = findVenvPython();
if (venvPy && tryExec(venvPy, ["-m", "polyharness", ...args])) {
  process.exit(0);
}

console.error(
  `Error: Could not find PolyHarness.\n\nInstall the Python package:\n  pip install polyharness\n\nOr install from source:\n  git clone https://github.com/weijt606/polyharness.git && cd polyharness\n  pip install -e .`
);
process.exit(1);
