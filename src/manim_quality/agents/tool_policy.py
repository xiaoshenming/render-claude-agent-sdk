"""Generic per-run constraints for built-in Agent tools."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from manim_quality.contracts._json_values import freeze_json_object


@dataclass(frozen=True, slots=True)
class ToolInputPolicy:
    max_calls: int
    required_fields: Sequence[str] = ()
    integer_minimums: Mapping[str, int] = field(default_factory=dict)
    integer_maximums: Mapping[str, int] = field(default_factory=dict)
    clamp_integer_maximums: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_calls, bool)
            or not isinstance(self.max_calls, int)
            or self.max_calls <= 0
        ):
            raise ValueError("max_calls must be a positive integer")
        required = tuple(self.required_fields)
        if any(not isinstance(item, str) or not item for item in required):
            raise ValueError("required_fields must contain non-empty strings")
        if len(set(required)) != len(required):
            raise ValueError("required_fields must not contain duplicates")
        object.__setattr__(self, "required_fields", required)
        object.__setattr__(
            self,
            "integer_minimums",
            freeze_json_object(dict(self.integer_minimums), "integer_minimums"),
        )
        object.__setattr__(
            self,
            "integer_maximums",
            freeze_json_object(dict(self.integer_maximums), "integer_maximums"),
        )
        _validate_bounds(self.integer_minimums, "integer_minimums")
        _validate_bounds(self.integer_maximums, "integer_maximums")
        if not isinstance(self.clamp_integer_maximums, bool):
            raise TypeError("clamp_integer_maximums must be bool")

    def validate(self, value: Mapping[str, object]) -> None:
        self.normalize(value)

    def normalize(self, value: Mapping[str, object]) -> Mapping[str, object]:
        missing = set(self.required_fields) - value.keys()
        if missing:
            raise ValueError(f"required tool fields are missing: {sorted(missing)}")
        _check_bounds(value, self.integer_minimums, minimum=True)
        normalized = dict(value)
        if self.clamp_integer_maximums:
            _clamp_maximums(normalized, self.integer_maximums)
        else:
            _check_bounds(value, self.integer_maximums, minimum=False)
        return freeze_json_object(normalized, "normalized_tool_policy_input")


def _validate_bounds(value: Mapping[str, object], name: str) -> None:
    for field_name, limit in value.items():
        if not isinstance(field_name, str) or not field_name:
            raise ValueError(f"{name} keys must be non-empty strings")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError(f"{name} values must be integers")


def _check_bounds(
    value: Mapping[str, object], bounds: Mapping[str, object], *, minimum: bool
) -> None:
    for name, raw_limit in bounds.items():
        item = value.get(name)
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"tool field {name} must be an integer")
        limit = int(raw_limit)
        if minimum and item < limit:
            raise ValueError(f"tool field {name} is below minimum {limit}")
        if not minimum and item > limit:
            raise ValueError(f"tool field {name} exceeds maximum {limit}")


def _clamp_maximums(value: dict[str, object], bounds: Mapping[str, object]) -> None:
    for name, raw_limit in bounds.items():
        item = value.get(name)
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"tool field {name} must be an integer")
        value[name] = min(item, int(raw_limit))
