"""Versioned input schemas for the seven Quality Operator tools."""

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

READ_SOLUTION_SCHEMA = schema({"revision_id": STRING}, ("revision_id",))
CHECK_RELATION_SCHEMA = schema(
    {
        "relation": STRING,
        "operands": {"type": "array", "minItems": 1, "maxItems": 6},
        "expected": {},
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
APPLY_PATCH_SCHEMA = schema(
    {
        "base_revision_id": STRING,
        "base_code_hash": STRING,
        "scope": {"type": "string", "enum": ["logic", "layout"]},
        "old_text": STRING,
        "new_text": STRING,
        "finding_ids": {"type": "array", "minItems": 1, "maxItems": 12},
    },
    (
        "base_revision_id",
        "base_code_hash",
        "scope",
        "old_text",
        "new_text",
        "finding_ids",
    ),
)
REVISION_INPUT_SCHEMA = schema({"revision_id": STRING}, ("revision_id",))
