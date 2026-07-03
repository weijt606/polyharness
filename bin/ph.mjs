#!/usr/bin/env node

/**
 * ph — PolyHarness CLI wrapper for npm installations.
 *
 * This thin wrapper finds and invokes the Python `ph` CLI.
 * Resolution order:
 *   1. `ph` on PATH (pip-installed entry point) — skipped if that `ph` is
 *      this wrapper itself (npm's bin dir often shadows pip's), which used
 *      to cause infinite self-recursion.
 *   2. `python -m polyharness` (PYTHONPATH / editable install)
 *   3. Local .venv (auto-detect venv in cwd or parents)
 *
 * A strategy is only "not found" when the binary is missing (ENOENT) or the
 * module doesn't exist. A real non-zero exit from the CLI (e.g. "not a
 * workspace") is final: it is propagated as-is, never retried with the next
 * strategy (which would run the command's side effects twice).
 */

import { execFileSync } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import { delimiter, dirname, join } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const isWindows = process.platform === "win32";
const SELF = safeRealpath(fileURLToPath(import.meta.url));

function safeRealpath(p) {
  try {
    return realpathSync(p);
  } catch {
    return p;
  }
}

/** Run a command with fully inherited stdio. Returns:
 *  - "missing"          → binary not found; try the next strategy
 *  - exit code (number) → the command ran; this is the final result
 */
function run(cmd, cmdArgs) {
  try {
    execFileSync(cmd, cmdArgs, {
      stdio: "inherit",
      env: { ...process.env, PH_NPM_WRAPPER: "1" },
    });
    return 0;
  } catch (e) {
    if (e.code === "ENOENT") return "missing";
    return typeof e.status === "number" ? e.status : 1;
  }
}

/** True if `py` exists and has the polyharness module installed (quiet probe). */
function hasPolyharness(py) {
  try {
    execFileSync(py, ["-c", "import polyharness"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** First `ph` on PATH that is NOT this wrapper (avoids self-recursion). */
function findRealPh() {
  const exts = isWindows ? ["", ".cmd", ".exe", ".bat"] : [""];
  for (const dir of (process.env.PATH || "").split(delimiter)) {
    if (!dir) continue;
    for (const ext of exts) {
      const candidate = join(dir, `ph${ext}`);
      if (!existsSync(candidate)) continue;
      const real = safeRealpath(candidate);
      // Skip ourselves and npm's shim pointing back at us.
      if (real === SELF || real.includes("polyharness/bin/ph.mjs")) continue;
      return candidate;
    }
  }
  return null;
}

/** Walk up from cwd looking for a virtualenv python. */
function findVenvPython() {
  let dir = process.cwd();
  for (let i = 0; i < 10; i++) {
    const candidates = isWindows
      ? [join(dir, ".venv", "Scripts", "python.exe")]
      : [join(dir, ".venv", "bin", "python")];
    for (const candidate of candidates) {
      if (existsSync(candidate)) return candidate;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

// Re-entry guard: if a parent wrapper already delegated to us via PATH,
// don't recurse into PATH lookup again.
const reentered = process.env.PH_NPM_WRAPPER === "1";

// Strategy 1: real (pip-installed) `ph` on PATH
if (!reentered) {
  const realPh = findRealPh();
  if (realPh) {
    const result = run(realPh, args);
    if (result !== "missing") process.exit(result);
  }
}

// Strategy 2: python -m polyharness (probe quietly first, then run for real —
// so the CLI's own stdio streams live and its exit code is authoritative)
const pythons = isWindows ? ["python", "py", "python3"] : ["python3", "python"];
for (const py of pythons) {
  if (hasPolyharness(py)) {
    process.exit(run(py, ["-m", "polyharness", ...args]));
  }
}

// Strategy 3: auto-detect .venv
const venvPy = findVenvPython();
if (venvPy && hasPolyharness(venvPy)) {
  process.exit(run(venvPy, ["-m", "polyharness", ...args]));
}

console.error(
  `Error: Could not find PolyHarness.\n\nInstall the Python package:\n  pip install polyharness\n\nOr install from source:\n  git clone https://github.com/weijt606/polyharness.git && cd polyharness\n  pip install -e .`
);
process.exit(1);
