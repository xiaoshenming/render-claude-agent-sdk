"""Bounded subprocess helpers with artifact-backed output."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path


def run_to_artifacts(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    stdout_path: Path,
    stderr_path: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(env_overrides or {})
    # start_new_session puts the wrapper and every grandchild (for example
    # the docker run client) into one process group; on timeout the whole
    # group is killed so inherited pipes close and communicate() returns
    # instead of hanging on a surviving grandchild.
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _kill_process_group(process)
        stdout, stderr = process.communicate()
        stdout_path.write_text(
            _timeout_text(error.stdout) or stdout or "",
            encoding="utf-8",
        )
        stderr_path.write_text(
            _timeout_text(error.stderr) or stderr or "process timed out",
            encoding="utf-8",
        )
        raise
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def read_last_json_line(text: str) -> dict[str, object]:
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("subprocess did not emit a JSON object")
