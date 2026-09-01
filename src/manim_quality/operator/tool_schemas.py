"""Versioned input schemas for the eight Quality Operator tools."""

from .tool_contracts import schema

STRING = {"type": "string", "minLength": 1}
FINDING_SCHEMA = schema(
    {
        "finding_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "category": {"type": "string", "enum": ["logic", "layout"]},
        "severity": {"type": "string", "enum": ["blocking", "warning"]},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "acceptance_criteria": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2_000,
        },
    },
    (
        "finding_id",
        "category",
        "severity",
        "summary",
        "acceptance_criteria",
    ),
)

CHECK_RELATION_SCHEMA = schema(
    {
        "relation": STRING,
        "operands": {"type": "array", "minItems": 1, "maxItems": 6},
        "expected": {"type": "boolean"},
    },
    ("relation", "operands", "expected"),
)
RECORD_FINDINGS_SCHEMA = schema(
    {
        "findings": {
            "type": "array",
            "items": FINDING_SCHEMA,
            "maxItems": 12,
        }
    },
    ("findings",),
)
REVISION_INPUT_SCHEMA = schema({"revision_id": STRING}, ("revision_id",))
CURRENT_REVISION_SCHEMA = schema(
    {
        "revision_id": STRING,
        "finding_ids": {
            "type": "array",
            "items": STRING,
            "maxItems": 12,
            "uniqueItems": True,
        },
    },
    ("revision_id",),
)
