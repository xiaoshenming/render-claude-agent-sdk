from __future__ import annotations

import os
from collections.abc import Mapping

_SECRET_FRAGMENTS = (
    "API_KEY",
    "AUTH_TOKEN",
    "ACCESS_TOKEN",
    "SECRET",
    "PASSWORD",
    "PRIVATE_KEY",
)
_EXPLICIT_SECRET_NAMES = {
    "MANIM_E2E_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
}


def sanitized_subprocess_env(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if environ is None else environ
    sanitized = {
        key: value
        for key, value in source.items()
        if key not in _EXPLICIT_SECRET_NAMES
        and not any(fragment in key.upper() for fragment in _SECRET_FRAGMENTS)
    }
    sanitized["PYTHONIOENCODING"] = "utf-8"
    sanitized["PYTHONUTF8"] = "1"
    return sanitized
