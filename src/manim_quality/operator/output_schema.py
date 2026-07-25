"""Terminal structured output contract for the unified Quality Operator."""

OPERATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["submitted"]},
        "submitted_revision_id": {"type": "string", "minLength": 2},
        "code_hash": {"type": "string", "minLength": 71, "maxLength": 71},
        "problem_hash": {"type": "string", "minLength": 71, "maxLength": 71},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
    },
    "required": [
        "status",
        "submitted_revision_id",
        "code_hash",
        "problem_hash",
        "summary",
    ],
    "additionalProperties": False,
}
