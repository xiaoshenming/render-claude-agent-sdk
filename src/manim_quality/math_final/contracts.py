from __future__ import annotations

ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "enum": [
                "answer",
                "proof",
                "input",
                "identity",
                "narration",
                "diagram",
            ],
        },
        "impact": {"type": "string", "enum": ["core", "local", "none"]},
        "claim": {"type": "string", "minLength": 1, "maxLength": 500},
        "evidence": {"type": "string", "minLength": 1, "maxLength": 1_200},
        "correct_invariant": {"type": "string", "minLength": 1, "maxLength": 800},
        "affects_final_answer": {"type": "boolean"},
    },
    "required": [
        "domain",
        "impact",
        "claim",
        "evidence",
        "correct_invariant",
        "affects_final_answer",
    ],
    "additionalProperties": False,
}

REVIEW_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": [
                "pass",
                "core_math",
                "input_invalid",
                "source_mismatch",
                "minor",
                "diagram_fidelity",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string", "minLength": 1, "maxLength": 1_500},
        "issues": {"type": "array", "maxItems": 6, "items": ISSUE_SCHEMA},
    },
    "required": ["classification", "confidence", "summary", "issues"],
    "additionalProperties": False,
}

ARBITRATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": [
                "pass",
                "core_math",
                "input_invalid",
                "source_mismatch",
                "minor",
                "diagram_fidelity",
            ],
        },
        "confirmed_claim_indexes": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 11},
            "maxItems": 12,
        },
        "summary": {"type": "string", "minLength": 1, "maxLength": 1_500},
    },
    "required": ["classification", "confirmed_claim_indexes", "summary"],
    "additionalProperties": False,
}
