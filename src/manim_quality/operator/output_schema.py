"""Terminal structured output contract for the unified Quality Operator."""

# "submitted" must bind the real submission; "held" is the honest terminal
# for sessions that could not clear every blocking issue within budget —
# the outer gate still decides HOLD independently and rolls back to R0.
OPERATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["submitted", "held"]},
        "submitted_revision_id": {"type": "string", "minLength": 2},
        "code_hash": {"type": "string", "minLength": 71, "maxLength": 71},
        "problem_hash": {"type": "string", "minLength": 71, "maxLength": 71},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "hold_reason": {"type": "string", "minLength": 1, "maxLength": 500},
    },
    "required": ["status", "summary"],
    "additionalProperties": False,
}
