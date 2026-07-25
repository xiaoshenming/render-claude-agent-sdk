"""Reject repair directives from facts-only geometry payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

FORBIDDEN_KEYS = frozenset(
    {
        "expected_value",
        "expected_truth",
        "fix",
        "diagnosis",
        "move_point",
        "patch",
        "repair",
        "repair_hint",
        "repairable",
        "replacement",
        "severity",
        "should_fix",
        "target_position",
    }
)


def reject_forbidden(value: object, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in FORBIDDEN_KEYS:
                raise ValueError(f"{path} contains forbidden key: {key}")
            reject_forbidden(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            reject_forbidden(item, f"{path}[{index}]")
