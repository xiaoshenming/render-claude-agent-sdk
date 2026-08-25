"""Normalization for bounded Reviewer metadata."""

from __future__ import annotations

import json
from collections.abc import Mapping


def reviewer_payload(text: str, error_type: type[Exception]) -> Mapping[str, object]:
    value = raw_reviewer_payload(text, error_type)
    warnings: list[str] = []
    decision = value.get("decision")
    if decision not in {"pass", "needs_repair"}:
        decision = "needs_repair"
        warnings.append("invalid_or_missing_decision")
    diagnosis = value.get("diagnosis")
    if not isinstance(diagnosis, str) or not diagnosis.strip():
        diagnosis = "Reviewer 返回了非标准结构，原始结果已保留供父 Agent 核实。"
        warnings.append("invalid_or_missing_diagnosis")
    issues = value.get("issues")
    if not isinstance(issues, list):
        issues = []
        warnings.append("invalid_or_missing_issues")
    if len(issues) > 12:
        issues = issues[:12]
        warnings.append("issues_truncated")
    normalized_issues = [_normalize_issue(issue, warnings) for issue in issues]
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping):
        coverage = {}
        warnings.append("invalid_or_missing_coverage")
    try:
        confidence = normalize_confidence(value.get("confidence"), error_type)
    except error_type:
        confidence = 0.0
        warnings.append("invalid_or_missing_confidence")
    if warnings:
        decision = "needs_repair"
        coverage = {**coverage, "protocol_warnings": warnings}
    return {
        "decision": decision,
        "diagnosis": diagnosis,
        "issues": normalized_issues,
        "coverage": coverage,
        "confidence": confidence,
    }


def raw_reviewer_payload(
    text: str, error_type: type[Exception]
) -> Mapping[str, object]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise error_type("Reviewer ToolResult must be valid JSON") from error
    if not isinstance(value, Mapping):
        raise error_type("Reviewer ToolResult must be a JSON object")
    return value


def _normalize_issue(value: object, warnings: list[str]) -> Mapping[str, object]:
    required = {"type", "target", "evidence", "required_invariant", "repair_scope"}
    if not isinstance(value, Mapping):
        warnings.append("non_object_issue")
        value = {}
    evidence = value.get("evidence")
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    evidence = [item for item in evidence if isinstance(item, str)][:2]
    defaults = {
        "type": "unstructured_reviewer_finding",
        "target": "Solution",
        "required_invariant": "核实 Reviewer 原始结论并修复确认的问题。",
        "repair_scope": "Solution",
    }
    normalized: dict[str, object] = {"evidence": evidence}
    for name in required - {"evidence"}:
        item = value.get(name)
        if not isinstance(item, str) or not item.strip():
            item = defaults[name]
            warnings.append(f"issue_{name}_defaulted")
        normalized[name] = item
    return normalized


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
