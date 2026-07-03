# Security Policy

PolyHarness optimizes the *harness* around an AI agent by repeatedly proposing,
running, and scoring candidate code. Because it **executes code** — both the
harness/evaluate scripts in your workspace and, indirectly, whatever an agent
backend writes — its security model is worth understanding before you run it on
anything sensitive.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | ✅ Yes     |
| < 0.3   | ❌ No — please upgrade |

Security fixes land on the latest minor release. PolyHarness is pre-1.0
(Development Status: Alpha); pin a version if you need stability.

## Reporting a Vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately through either channel:

- **GitHub Security Advisories** (preferred): the *Security → Report a
  vulnerability* tab on the repository, which opens a private advisory.
- **Email**: `weijt606@gmail.com` with `[PolyHarness Security]` in the subject.

Please include: affected version, a description, and a minimal reproduction if
possible. We aim to acknowledge within 5 business days and to coordinate a fix
and disclosure timeline with you. There is no paid bounty program, but we credit
reporters in the release notes unless you prefer to remain anonymous.

## Security Model — read this before running

PolyHarness is a **local developer tool**, not a sandbox or a multi-tenant
service. The following are deliberate design boundaries, not bugs:

1. **The evaluator is not a sandbox.** `evaluate.py` and the candidate harness
   code run as ordinary subprocesses with **your** filesystem and network
   permissions. Do not point PolyHarness at task sets or harness code you do not
   trust.
2. **Agent backends run with their own privileges.** CLI backends
   (`claude-code`, `codex`, `pi`, …) have *different* isolation postures — some
   gate file writes, some gate nothing. Treat a proposer backend as capable of
   doing anything the underlying agent can do in the workspace directory.
3. **Generated code is executed, not just read.** The `code-generation` template
   `exec()`s model output with the evaluation process's full permissions. This
   is acceptable for evaluating *your own* harness's output; it is not safe for
   arbitrary untrusted code.

### What PolyHarness *does* protect against (v0.3.0+)

These are **tamper-evidence and accident-prevention** measures — they raise the
bar and catch mistakes/reward-hacking, but they are **not a jail**:

- **Proposer file tools are path-contained** (`resolve()` + `is_relative_to`), so
  an API/OpenAI proposer cannot read or write outside the workspace / its own
  candidate directory. There is intentionally **no shell tool**.
- **Evaluation integrity is verified**: the evaluate script and task files are
  hashed at run start and re-checked before every evaluation; any mid-run
  modification aborts the run instead of logging fake scores.
- **Held-out test tasks are isolated** from the search so a proposer cannot
  overfit to them, then restored hash-verified for the final score.
- **Subprocesses run as process groups** and are killed wholesale on timeout, so
  a runaway agent/eval can't orphan grandchildren that keep running.
- **Secrets are not echoed**: `ph config show` masks `api_key`, and credentials
  are read from environment variables by default.

### Hardening recommendations

- Run PolyHarness inside a **container or VM** when working with untrusted
  harnesses, tasks, or agent output.
- Provide API keys via **environment variables**, never committed to
  `config.yaml`.
- Review the candidate diffs (`ph compare`, `ph diff`) before `ph apply` writes
  a result back into your project.

## Scope

In scope: sandbox-escape beyond the documented boundaries above, path-traversal
in the proposer tools, integrity-check bypass, credential leakage, and
supply-chain issues in the published PyPI/npm artifacts.

Out of scope: the documented design boundaries (evaluator is not a sandbox;
agent backends run with their own privileges; generated code is executed) — these
are inherent to what the tool does and are not treated as vulnerabilities.
