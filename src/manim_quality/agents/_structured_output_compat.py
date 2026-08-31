"""Small provider compatibility adapter for SDK structured output."""

from __future__ import annotations

from collections.abc import Mapping

from ..contracts._json_values import thaw_json_object


def adapt_structured_output(
    value: object, schema: Mapping[str, object]
) -> object:
    """Keep declared fields and bound strings without inventing decisions."""
    return _adapt_value(value, schema)


def _adapt_value(value: object, rule: Mapping[str, object]) -> object:
    if isinstance(value, Mapping):
        properties = rule.get("properties")
        if not isinstance(properties, Mapping):
            return value
        return {
            name: _adapt_value(value[name], child)
            for name, child in properties.items()
            if isinstance(name, str)
            and name in value
            and isinstance(child, Mapping)
        }
    if isinstance(value, list):
        items = rule.get("items")
        if isinstance(items, Mapping):
            return [_adapt_value(item, items) for item in value]
        return value
    if isinstance(value, str):
        limit = rule.get("maxLength")
        if isinstance(limit, int) and limit >= 0:
            return value[:limit]
    return value


def relaxed_provider_schema(schema: Mapping[str, object]) -> dict[str, object]:
    """Relax transport syntax while preserving required semantic fields."""
    relaxed = thaw_json_object(schema)
    _relax_rule(relaxed)
    return relaxed


def _relax_rule(rule: object) -> None:
    if isinstance(rule, list):
        for item in rule:
            _relax_rule(item)
        return
    if not isinstance(rule, dict):
        return
    rule.pop("maxLength", None)
    if rule.get("type") == "object" or isinstance(rule.get("properties"), dict):
        rule["additionalProperties"] = True
    for item in rule.values():
        _relax_rule(item)
