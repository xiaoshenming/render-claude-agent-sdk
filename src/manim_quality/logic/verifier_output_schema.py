"""Structured evidence schema for the directed Logic Verifier."""

_EVIDENCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scene_id", "line_start", "line_end", "excerpt"],
    "properties": {
        "scene_id": {"type": "string", "minLength": 1},
        "line_start": {"type": "integer", "minimum": 1},
        "line_end": {"type": "integer", "minimum": 1},
        "excerpt": {"type": "string", "minLength": 1},
    },
}

VERIFIER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "results", "review_gaps"],
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["verified", "rejected", "human_review"],
        },
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "issue_id",
                    "resolved",
                    "reason",
                ],
                "properties": {
                    "issue_id": {"type": "string", "minLength": 1},
                    "resolved": {"type": "boolean"},
                    "candidate_evidence": {
                        "anyOf": [_EVIDENCE, {"type": "null"}],
                    },
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
        "review_gaps": {"type": "array", "items": {"type": "string"}},
    },
}
