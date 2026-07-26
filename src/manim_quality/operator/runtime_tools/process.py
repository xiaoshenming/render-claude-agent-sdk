"""Bounded subprocess helpers with artifact-backed output."""

from __future__ import annotations

import json
import os
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
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        stdout_path.write_text(_timeout_text(error.stdout), encoding="utf-8")
        stderr_path.write_text(
            _timeout_text(error.stderr) or "process timed out",
            encoding="utf-8",
        )
        raise
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    return result


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
