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
RECEIPT_STATUSES = frozenset({"complete", "risk", "incomplete"})
ISSUE_SEVERITIES = frozenset(
    {"info", "warning", "medium", "high", "blocking", "critical"}
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
                    "tool": {"type": "string", "enum": sorted(REQUIRED_TOOLS)},
                    "status": {"type": "string", "enum": sorted(RECEIPT_STATUSES)},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "uniqueItems": True,
                    },
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
                    "severity": {
                        "type": "string",
                        "enum": sorted(ISSUE_SEVERITIES),
                    },
                    "category": {"type": "string", "minLength": 1},
                    "summary": {"type": "string", "minLength": 1},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                        "uniqueItems": True,
                    },
                },
                "required": ["severity", "category", "summary", "evidence_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "summary", "tool_receipts", "issues"],
    "additionalProperties": False,
}


def validate_assurance_output(
    value: Mapping[str, object],
    *,
    expected_reports: Mapping[str, Mapping[str, object]] | None = None,
) -> None:
    status = value.get("status")
    if status not in {"pass", "review", "incomplete"}:
        raise ValueError("invalid assurance status")
    receipts = value.get("tool_receipts")
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ValueError("tool_receipts must be an array")
    rows = [row for row in receipts if isinstance(row, Mapping)]
    if len(rows) != len(receipts):
        raise ValueError("tool receipts must contain objects")
    names = [row.get("tool") for row in rows]
    missing = REQUIRED_TOOLS - set(names)
    if missing:
        raise ValueError(f"required tool receipts missing: {sorted(missing)}")
    if len(names) != len(REQUIRED_TOOLS) or len(set(names)) != len(names):
        raise ValueError("tool receipts must contain every required tool exactly once")
    _validate_receipts(rows, expected_reports)
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
    _validate_issues(issues, rows, expected_reports)
    _validate_top_level_status(status, rows, issues)


def _validate_receipts(
    receipts: Sequence[Mapping[str, object]],
    expected_reports: Mapping[str, Mapping[str, object]] | None,
) -> None:
    for row in receipts:
        name = row.get("tool")
        status = row.get("status")
        evidence_ids = row.get("evidence_ids")
        if status not in RECEIPT_STATUSES:
            raise ValueError(f"invalid receipt status for {name}")
        if not _text_sequence(evidence_ids):
            raise ValueError(f"invalid evidence ids for {name}")
        if expected_reports is None:
            continue
        expected = expected_reports.get(str(name))
        if expected is None:
            raise ValueError(f"missing observed report for {name}")
        if status != expected.get("status"):
            raise ValueError(
                f"receipt status does not match observed report for {name}"
            )
        actual_ids = _evidence_ids(expected.get("evidence"))
        if set(evidence_ids) != actual_ids:
            raise ValueError(
                f"receipt evidence does not match observed report for {name}"
            )


def _validate_issues(
    issues: Sequence[object],
    receipts: Sequence[Mapping[str, object]],
    expected_reports: Mapping[str, Mapping[str, object]] | None,
) -> None:
    receipt_ids = {
        evidence_id
        for row in receipts
        for evidence_id in row.get("evidence_ids", ())
        if isinstance(evidence_id, str)
    }
    allowed_ids = receipt_ids | {
        "reviewer:math_geometry_reviewer",
        "reviewer:animation_lifecycle_reviewer",
        "reviewer:visual_layout_reviewer",
    }
    for issue in issues:
        if not isinstance(issue, Mapping):
            raise ValueError("issues must contain objects")
        if issue.get("severity") not in ISSUE_SEVERITIES:
            raise ValueError("invalid issue severity")
        evidence_ids = issue.get("evidence_ids")
        if not _text_sequence(evidence_ids):
            raise ValueError("every issue must cite evidence")
        if expected_reports is not None and not set(evidence_ids) <= allowed_ids:
            raise ValueError("issue cites unknown evidence")


def _validate_top_level_status(
    status: object,
    receipts: Sequence[Mapping[str, object]],
    issues: Sequence[object],
) -> None:
    statuses = {row.get("status") for row in receipts}
    expected = (
        "incomplete"
        if "incomplete" in statuses
        else ("review" if "risk" in statuses or issues else "pass")
    )
    if status != expected:
        raise ValueError(f"top-level status must be {expected}")


def _text_sequence(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == len(set(value))
        and all(isinstance(item, str) and item for item in value)
    )


def _evidence_ids(value: object) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {
        str(row["id"])
        for row in value
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }
