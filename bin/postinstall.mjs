#!/usr/bin/env node

/**
 * postinstall — attempt to install the Python package automatically.
 * Runs after `npm install polyharness` (or `npm install -g polyharness`).
 * Silent failure is OK — user can install pip package manually.
 */

import { execSync } from "node:child_process";

function isInstalled() {
  try {
    execSync('python3 -c "import polyharness"', { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function tryInstall(cmd) {
  try {
    execSync(cmd, { stdio: "inherit" });
    return true;
  } catch {
    return false;
  }
}

if (isInstalled()) {
  console.log("✅ polyharness Python package already installed.");
  process.exit(0);
}

console.log("Installing polyharness Python package...");

// Try uv first (fast), then pip3, then pip
const strategies = [
  "uv pip install polyharness",
  "pip3 install polyharness",
  "pip install polyharness",
];

for (const cmd of strategies) {
  if (tryInstall(cmd)) {
    console.log("✅ polyharness installed successfully.");
    process.exit(0);
  }
}

console.warn(
  "⚠️  Could not auto-install Python package. Please run manually:\n" +
    "   pip install polyharness"
);
process.exit(0); // non-fatal — npm install should still succeed
