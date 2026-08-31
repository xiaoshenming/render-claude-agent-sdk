from types import MappingProxyType

from manim_quality.agents._structured_output_compat import (
    adapt_structured_output,
    relaxed_provider_schema,
)


def test_adapter_removes_provider_extras_and_bounds_strings() -> None:
    schema = {
        "properties": {
            "status": {"type": "string"},
            "summary": {"type": "string", "maxLength": 5},
        },
        "additionalProperties": False,
    }

    assert adapt_structured_output(
        {"status": "held", "summary": "123456", "provider_note": "x"}, schema
    ) == {"status": "held", "summary": "12345"}


def test_adapter_does_not_invent_missing_semantic_fields() -> None:
    schema = {"properties": {"status": {"type": "string"}}}

    assert adapt_structured_output({"summary": "only prose"}, schema) == {}


def test_adapter_recursively_normalizes_objects_and_arrays() -> None:
    schema = {
        "type": "object",
        "properties": {
            "coverage": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "maxLength": 5},
                },
                "additionalProperties": False,
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }

    assert adapt_structured_output(
        {
            "coverage": {"summary": "123456", "provider_note": "drop"},
            "issues": [{"target": "line 1", "provider_note": "drop"}],
        },
        schema,
    ) == {
        "coverage": {"summary": "12345"},
        "issues": [{"target": "line 1"}],
    }


def test_deepseek_schema_keeps_required_fields_but_accepts_provider_extras() -> None:
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["held"]},
            "summary": {"type": "string", "maxLength": 5},
        },
        "required": ["status", "summary"],
        "additionalProperties": False,
    }

    relaxed = relaxed_provider_schema(schema)

    assert relaxed["required"] == ["status", "summary"]
    assert relaxed["additionalProperties"] is True
    assert "maxLength" not in relaxed["properties"]["summary"]
    assert schema["additionalProperties"] is False


def test_deepseek_schema_thaws_nested_frozen_json() -> None:
    schema = MappingProxyType({
        "type": "object",
        "properties": MappingProxyType({
            "status": MappingProxyType({
                "type": "string", "enum": ("held",), "maxLength": 5,
            }),
        }),
        "required": ("status",),
        "additionalProperties": False,
    })

    relaxed = relaxed_provider_schema(schema)

    assert relaxed == {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["held"]}},
        "required": ["status"],
        "additionalProperties": True,
    }


def test_relaxed_schema_recursively_accepts_provider_extras() -> None:
    schema = {
        "type": "object",
        "properties": {
            "coverage": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "maxLength": 5},
                },
                "additionalProperties": False,
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }

    relaxed = relaxed_provider_schema(schema)

    assert relaxed["additionalProperties"] is True
    assert relaxed["properties"]["coverage"]["additionalProperties"] is True
    assert "maxLength" not in relaxed["properties"]["coverage"]["properties"][
        "summary"
    ]
    assert relaxed["properties"]["issues"]["items"][
        "additionalProperties"
    ] is True
