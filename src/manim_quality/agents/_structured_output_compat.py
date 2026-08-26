"""Small provider compatibility adapter for SDK structured output."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy


def adapt_structured_output(
    value: object, schema: Mapping[str, object]
) -> object:
    """Keep declared fields and bound strings without inventing decisions."""
    if not isinstance(value, Mapping):
        return value
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return value
    adapted: dict[str, object] = {}
    for name, rule in properties.items():
        if not isinstance(name, str) or name not in value:
            continue
        item = value[name]
        if isinstance(rule, Mapping) and isinstance(item, str):
            limit = rule.get("maxLength")
            if isinstance(limit, int) and limit >= 0:
                item = item[:limit]
        adapted[name] = item
    return adapted


def relaxed_provider_schema(schema: Mapping[str, object]) -> dict[str, object]:
    """Let provider extras reach hooks while keeping required semantic fields."""
    relaxed = deepcopy(dict(schema))
    relaxed["additionalProperties"] = True
    properties = relaxed.get("properties")
    if isinstance(properties, dict):
        for rule in properties.values():
            if isinstance(rule, dict):
                rule.pop("maxLength", None)
    return relaxed
