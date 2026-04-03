#!/usr/bin/env node

/**
 * postinstall — attempt to install the Python package automatically.
 * Runs after `npm install poly-harness` (or `npm install -g poly-harness`).
 * Silent failure is OK — user can install pip package manually.
 */

import { execSync } from "node:child_process";

function isInstalled() {
  try {
    execSync('python3 -c "import poly_harness"', { stdio: "ignore" });
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
  console.log("✅ poly-harness Python package already installed.");
  process.exit(0);
}

console.log("Installing poly-harness Python package...");

// Try uv first (fast), then pip3, then pip
const strategies = [
  "uv pip install poly-harness",
  "pip3 install poly-harness",
  "pip install poly-harness",
];

for (const cmd of strategies) {
  if (tryInstall(cmd)) {
    console.log("✅ poly-harness installed successfully.");
    process.exit(0);
  }
}

console.warn(
  "⚠️  Could not auto-install Python package. Please run manually:\n" +
    "   pip install poly-harness"
);
process.exit(0); // non-fatal — npm install should still succeed
