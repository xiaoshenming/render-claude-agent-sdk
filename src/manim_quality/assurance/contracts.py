from __future__ import annotations

from collections.abc import Mapping, Sequence

REQUIRED_TOOLS = frozenset(
    {
        "inspect_artifact",
        "inspect_execution",
        "inspect_code_review",
        "inspect_layout",
        "inspect_risk_frames",
        "inspect_tts",
        "inspect_consistency",
    }
)

ASSURANCE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["pass", "review", "incomplete"]},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "tool_receipts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "status": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["tool", "status", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string"},
                    "category": {"type": "string"},
                    "summary": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["severity", "category", "summary", "evidence_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "summary", "tool_receipts", "issues"],
    "additionalProperties": False,
}


def validate_assurance_output(value: Mapping[str, object]) -> None:
    status = value.get("status")
    if status not in {"pass", "review", "incomplete"}:
        raise ValueError("invalid assurance status")
    receipts = value.get("tool_receipts")
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ValueError("tool_receipts must be an array")
    names = {
        row.get("tool")
        for row in receipts
        if isinstance(row, Mapping) and isinstance(row.get("tool"), str)
    }
    missing = REQUIRED_TOOLS - names
    if missing:
        raise ValueError(f"required tool receipts missing: {sorted(missing)}")
    issues = value.get("issues")
    if not isinstance(issues, Sequence) or isinstance(issues, (str, bytes)):
        raise ValueError("issues must be an array")
    if status == "pass":
        risky = [
            row
            for row in issues
            if isinstance(row, Mapping)
            and row.get("severity") in {"high", "blocking", "critical"}
        ]
        incomplete = [
            row
            for row in receipts
            if isinstance(row, Mapping) and row.get("status") != "complete"
        ]
        if risky or incomplete:
            raise ValueError("pass cannot contain risk or incomplete evidence")
