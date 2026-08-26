"""Small provider compatibility adapter for SDK structured output."""

from __future__ import annotations

from collections.abc import Mapping


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
