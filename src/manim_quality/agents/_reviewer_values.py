"""Normalization for bounded Reviewer metadata."""

from __future__ import annotations

import json
from collections.abc import Mapping


def reviewer_payload(
    text: str, error_type: type[Exception]
) -> Mapping[str, object]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise error_type("Reviewer ToolResult must be valid JSON") from error
    if not isinstance(value, Mapping):
        raise error_type("Reviewer ToolResult must be a JSON object")
    required = {"decision", "diagnosis", "issues", "coverage", "confidence"}
    if not required.issubset(value):
        raise error_type("Reviewer ToolResult has invalid fields")
    if value["decision"] not in {"pass", "needs_repair"}:
        raise error_type("Reviewer decision is invalid")
    if not isinstance(value["diagnosis"], str):
        raise error_type("Reviewer diagnosis must be text")
    issues = value["issues"]
    if not isinstance(issues, list) or len(issues) > 12:
        raise error_type("Reviewer issues must contain at most 12 items")
    normalized_issues = [_normalize_issue(issue, error_type) for issue in issues]
    if not isinstance(value["coverage"], Mapping):
        raise error_type("Reviewer coverage must be an object")
    normalized = {name: value[name] for name in required}
    normalized["issues"] = normalized_issues
    normalized["confidence"] = normalize_confidence(value["confidence"], error_type)
    return normalized


def _normalize_issue(
    value: object, error_type: type[Exception]
) -> Mapping[str, object]:
    required = {"type", "target", "evidence", "required_invariant", "repair_scope"}
    if not isinstance(value, Mapping) or not required.issubset(value):
        raise error_type("Reviewer issue has invalid fields")
    evidence = value["evidence"]
    if (
        not isinstance(evidence, list)
        or len(evidence) > 2
        or any(not isinstance(item, str) for item in evidence)
    ):
        raise error_type("Reviewer issue evidence exceeds its bound")
    for name in required - {"evidence"}:
        if not isinstance(value[name], str) or not value[name].strip():
            raise error_type(f"Reviewer issue {name} must be text")
    return {name: value[name] for name in required}


def normalize_confidence(value: object, error_type: type[Exception]) -> float:
    if isinstance(value, bool):
        raise error_type("Reviewer confidence is invalid")
    if isinstance(value, str):
        qualitative = {"high": 0.9, "medium": 0.6, "low": 0.3}
        mapped = qualitative.get(value.strip().lower())
        if mapped is not None:
            return mapped
    percent = isinstance(value, str) and value.strip().endswith("%")
    if percent:
        value = value.strip()[:-1]
    try:
        confidence = float(value)
    except (TypeError, ValueError) as error:
        raise error_type("Reviewer confidence is invalid") from error
    if percent or 1 < confidence <= 100:
        confidence /= 100
    if not 0 <= confidence <= 1:
        raise error_type("Reviewer confidence must be between 0 and 1")
    return confidence
