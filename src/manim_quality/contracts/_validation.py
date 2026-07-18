"""Validation primitives owned by the public contract package."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import TypeVar

EnumT = TypeVar("EnumT", bound=StrEnum)


def validate_contract_dict(
    data: object,
    fields: frozenset[str],
    schema_version: int,
    contract_name: str,
) -> dict[str, object]:
    if type(data) is not dict:
        raise TypeError(f"{contract_name} must be decoded from a JSON object")
    if any(type(key) is not str for key in data):
        raise TypeError(f"{contract_name} field names must be strings")
    missing = sorted(fields - data.keys())
    if missing:
        raise ValueError(f"{contract_name} missing field(s): {', '.join(missing)}")
    unknown = sorted(data.keys() - fields)
    if unknown:
        raise ValueError(f"{contract_name} unknown field(s): {', '.join(unknown)}")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != schema_version
    ):
        raise ValueError(
            f"{contract_name} schema_version must be {schema_version}, "
            f"got {data['schema_version']!r}"
        )
    return data


def require_non_empty_string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def require_optional_string(
    value: object,
    field_name: str,
    *,
    allow_empty: bool = False,
) -> str | None:
    if value is None:
        return None
    if allow_empty:
        if type(value) is not str:
            raise TypeError(f"{field_name} must be a string or null")
        return value
    return require_non_empty_string(value, field_name)


def require_enum(value: object, enum_type: type[EnumT], field_name: str) -> EnumT:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{field_name} has invalid value {value!r}") from error


def require_wire_object(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{field_name} must be a JSON object")
    return value


def require_wire_array(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{field_name} must be a JSON array")
    return value


def freeze_string_mapping(value: object, field_name: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    frozen: dict[str, str] = {}
    for key, item in value.items():
        valid_key = require_non_empty_string(key, f"{field_name} key")
        frozen[valid_key] = require_non_empty_string(
            item, f"{field_name}[{valid_key!r}]"
        )
    return MappingProxyType(dict(sorted(frozen.items())))


def freeze_identifier_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be an array")
    identifiers = tuple(
        require_non_empty_string(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{field_name} must not contain duplicates")
    if type(value) is tuple:
        return value
    return identifiers


def freeze_string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be an array")
    frozen = tuple(
        require_non_empty_string(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if type(value) is tuple:
        return value
    return frozen


def freeze_non_negative_int_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    frozen: dict[str, int] = {}
    for key, item in value.items():
        valid_key = require_non_empty_string(key, f"{field_name} key")
        frozen[valid_key] = require_non_negative_int(
            item, f"{field_name}[{valid_key!r}]"
        )
    return MappingProxyType(dict(sorted(frozen.items())))


def require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value
