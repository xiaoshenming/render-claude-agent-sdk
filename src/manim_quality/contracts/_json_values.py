"""Deep freeze and thaw JSON objects used by public contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

MAX_JSON_DEPTH = 64


def freeze_json_object(value: object, field_name: str) -> Mapping[str, object]:
    """Normalize and recursively freeze one Python JSON-like mapping."""
    return _freeze_object(value, field_name, wire=False)


def freeze_wire_json_object(value: object, field_name: str) -> Mapping[str, object]:
    """Strictly validate and freeze a native JSON object from the wire."""
    return _freeze_object(value, field_name, wire=True)


def thaw_json_object(value: Mapping[str, object]) -> dict[str, object]:
    """Return a detached, ordinary JSON object from a frozen object."""
    return {key: _thaw_json(item) for key, item in value.items()}


def _freeze_object(
    value: object,
    field_name: str,
    *,
    wire: bool,
) -> Mapping[str, object]:
    if (wire and type(value) is not dict) or (
        not wire and not isinstance(value, Mapping)
    ):
        raise TypeError(f"{field_name} must be a JSON object")
    try:
        return cast(
            Mapping[str, object],
            _freeze_json(value, field_name, depth=1, wire=wire),
        )
    except RecursionError as error:
        raise ValueError(
            f"{field_name} exceeds maximum JSON depth {MAX_JSON_DEPTH}"
        ) from error


def _freeze_json(value: object, path: str, *, depth: int, wire: bool) -> object:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain finite JSON numbers")
        return value
    if (wire and type(value) is dict) or (not wire and isinstance(value, Mapping)):
        return _freeze_mapping(value, path, depth=depth, wire=wire)
    if (wire and type(value) is list) or (
        not wire and not isinstance(value, (str, bytes)) and isinstance(value, Sequence)
    ):
        return _freeze_sequence(value, path, depth=depth, wire=wire)
    raise TypeError(f"{path} contains a non-JSON value: {type(value).__name__}")


def _freeze_mapping(
    value: Mapping[object, object],
    path: str,
    *,
    depth: int,
    wire: bool,
) -> Mapping[str, object]:
    _require_depth(depth, path)
    for key in value:
        if type(key) is not str:
            raise TypeError(f"{path} must contain only string object keys")
    return MappingProxyType(
        {
            key: _freeze_json(value[key], f"{path}.{key}", depth=depth + 1, wire=wire)
            for key in sorted(value)
        }
    )


def _freeze_sequence(
    value: Sequence[object],
    path: str,
    *,
    depth: int,
    wire: bool,
) -> tuple[object, ...]:
    _require_depth(depth, path)
    frozen = tuple(
        _freeze_json(item, f"{path}[{index}]", depth=depth + 1, wire=wire)
        for index, item in enumerate(value)
    )
    if type(value) is tuple and all(
        frozen_item is item for frozen_item, item in zip(frozen, value, strict=True)
    ):
        return value
    return frozen


def _require_depth(depth: int, path: str) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"{path} exceeds maximum JSON depth {MAX_JSON_DEPTH}")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    return value
