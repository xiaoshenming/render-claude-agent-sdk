"""Structured completion schema for the Scene-scoped Logic Coder."""

CODER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "risk_flags"],
    "properties": {
        "status": {"type": "string", "enum": ["patched", "no_change"]},
        "summary": {"type": "string", "minLength": 1},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
}
