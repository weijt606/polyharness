"""Subprocess helpers with reliable timeout semantics.

`subprocess.run(timeout=...)` only kills the direct child. Agent CLIs and
evaluate scripts routinely fork grandchildren (node runtimes, tool
subprocesses, LLM calls) that survive the kill, keep spending money, and can
keep writing into the workspace — and their inherited pipe ends can make the
follow-up `communicate()` block forever. Running the child as its own session
leader lets us kill the entire process group on timeout.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass


@dataclass
class ProcResult:
    """Outcome of a group-managed subprocess run."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_process_group(
    cmd: list[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> ProcResult:
    """Run `cmd`, killing its whole process group if `timeout` elapses.

    On timeout, partial stdout/stderr captured so far is preserved in the
    result (`timed_out=True`) instead of being discarded.

    Raises FileNotFoundError / PermissionError as subprocess.Popen would.
    """
    posix = os.name == "posix"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        start_new_session=posix,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return ProcResult(proc.returncode, stdout or "", stderr or "", timed_out=False)
    except subprocess.TimeoutExpired as exc:
        _kill_group(proc, posix=posix)
        try:
            rest_out, rest_err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            rest_out, rest_err = "", ""
        stdout = _as_text(exc.stdout) or rest_out or ""
        stderr = _as_text(exc.stderr) or rest_err or ""
        return ProcResult(-1, stdout, stderr, timed_out=True)


def _kill_group(proc: subprocess.Popen, *, posix: bool) -> None:
    if posix:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    proc.kill()


def _as_text(data: object) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)
