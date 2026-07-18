"""Private Claude SDK environment loading."""

from __future__ import annotations

import os
import shlex
import stat
from pathlib import Path

DEFAULT_SDK_ENV_PATH = Path.home() / ".config" / "mathpi" / "quality_repair_sdk.env"
SDK_ENV_PATH_VAR = "QUALITY_REPAIR_SDK_ENV"
PRIVATE_SDK_ENV_KEYS = {"ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "QUALITY_REPAIR_SDK_MODEL"}
SDK_PROCESS_ENV_KEYS = {"ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"}
SCRUB_SDK_ENV_KEYS = SDK_PROCESS_ENV_KEYS | {"ANTHROPIC_AUTH_TOKEN"}


def _load_persistent_sdk_env(path: Path | None = None) -> dict[str, str]:
    """Load long-lived Claude SDK env from a private local file."""
    env_path = path or Path(os.environ.get(SDK_ENV_PATH_VAR, DEFAULT_SDK_ENV_PATH)).expanduser()
    if not env_path.exists():
        return {}
    mode = stat.S_IMODE(env_path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(f"sdk_env_insecure_permissions:{env_path}:expected_600")
    values = _parse_sdk_env_file(env_path)
    for key in SCRUB_SDK_ENV_KEYS:
        if key in values:
            os.environ[key] = values[key]
        else:
            os.environ.pop(key, None)
    return values


def _parse_sdk_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, raw_value = line.partition("=")
        key = key.strip()
        if sep != "=" or key not in PRIVATE_SDK_ENV_KEYS:
            continue
        values[key] = _parse_sdk_env_value(raw_value.strip())
    return values


def _parse_sdk_env_value(value: str) -> str:
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        parts = list(lexer)
    except ValueError:
        return value.strip("\"'")
    if len(parts) == 1:
        return parts[0]
    return value.strip("\"'")
