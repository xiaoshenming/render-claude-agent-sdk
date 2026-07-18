"""Strict SDK structured-output schema for the Logic Reviewer."""

from __future__ import annotations

from typing import Final

_CITATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["artifact", "scene_id", "line_start", "line_end", "excerpt"],
    "properties": {
        "artifact": {
            "type": "string",
            "enum": [
                "candidate_code",
                "problem_text",
                "planning",
                "expected_answer",
                "render_manifest",
            ],
        },
        "scene_id": {"type": ["string", "null"]},
        "line_start": {"type": ["integer", "null"], "minimum": 1},
        "line_end": {"type": ["integer", "null"], "minimum": 1},
        "excerpt": {"type": "string", "minLength": 1},
    },
}

_CANDIDATE_CITATION_SCHEMA = {
    **_CITATION_SCHEMA,
    "properties": {
        **_CITATION_SCHEMA["properties"],
        "artifact": {"type": "string", "enum": ["candidate_code"]},
        "line_start": {"type": "integer", "minimum": 1},
        "line_end": {"type": "integer", "minimum": 1},
    },
}

_EXPECTED_CITATION_SCHEMA = {
    **_CITATION_SCHEMA,
    "properties": {
        **_CITATION_SCHEMA["properties"],
        "artifact": {
            "type": "string",
            "enum": ["problem_text", "planning", "expected_answer"],
        },
        "scene_id": {"type": "null"},
        "line_start": {"type": "null"},
        "line_end": {"type": "null"},
    },
}

_ISSUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "issue_id",
        "issue_type",
        "severity",
        "confidence",
        "repairable",
        "repair_scope",
        "target_scene_ids",
        "candidate_evidence",
        "expected_evidence",
        "supporting_evidence",
        "expected",
        "observed",
        "acceptance_predicates",
        "non_goals",
    ],
    "properties": {
        "issue_id": {"type": "string", "minLength": 1},
        "issue_type": {"type": "string", "minLength": 1},
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "repairable": {"type": "boolean"},
        "repair_scope": {"type": "string", "minLength": 1},
        "target_scene_ids": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "candidate_evidence": {
            "type": "array",
            "minItems": 1,
            "items": _CANDIDATE_CITATION_SCHEMA,
        },
        "expected_evidence": {
            "type": "array",
            "minItems": 1,
            "items": _EXPECTED_CITATION_SCHEMA,
        },
        "supporting_evidence": {
            "type": "array",
            "items": _CITATION_SCHEMA,
        },
        "expected": {"type": "string", "minLength": 1},
        "observed": {"type": "string", "minLength": 1},
        "acceptance_predicates": {"type": "array", "items": {"type": "object"}},
        "non_goals": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
}

REVIEW_OUTPUT_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision",
        "blocked",
        "requires_human_review",
        "summary",
        "issues",
        "review_gaps",
    ],
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["pass", "needs_repair", "record_only", "human_review"],
        },
        "blocked": {"type": "boolean"},
        "requires_human_review": {"type": "boolean"},
        "summary": {"type": "string", "minLength": 1},
        "issues": {"type": "array", "items": _ISSUE_SCHEMA},
        "review_gaps": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
}
