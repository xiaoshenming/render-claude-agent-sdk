from __future__ import annotations

from typing import Any


REPAIRABLE_VALUES = {
    "candidate",
    "direct",
    "repair",
    "supported",
    "auto",
    "auto_repair",
    "auto_repairable",
    "direct_replace",
    "direct_repair",
    "direct_repairable",
    "directly_repairable",
    "fixable_directly",
    "repairable",
}

SOFT_REPAIRABLE_VALUES = {
    "soft",
    "soft_repair",
    "soft_repairable",
    "llm_soft_repair",
    "agent_attempt",
}


def verify_review_payload(review: dict[str, Any], *, allow_soft_repair: bool = False) -> dict[str, Any]:
    sample_id = str(review.get("sample_id") or "unknown")
    verified_issues = [
        _verify_issue(sample_id, index, issue, allow_soft_repair=allow_soft_repair)
        for index, issue in enumerate(review.get("issues") or [], start=1)
        if isinstance(issue, dict)
    ]
    supported_count = sum(1 for issue in verified_issues if issue["verification_status"] == "supported")
    soft_supported_count = sum(1 for issue in verified_issues if issue["verification_status"] == "soft_supported")
    needs_human_review_count = sum(
        1 for issue in verified_issues if issue["verification_status"] == "needs_human_review"
    )
    return {
        "schema_version": "logic_engine_mvp.verified_issues.v1",
        "sample_id": sample_id,
        "issue_count": len(verified_issues),
        "supported_count": supported_count,
        "soft_supported_count": soft_supported_count,
        "needs_human_review_count": needs_human_review_count,
        "issues": verified_issues,
    }


def _verify_issue(
    sample_id: str,
    index: int,
    issue: dict[str, Any],
    *,
    allow_soft_repair: bool,
) -> dict[str, Any]:
    wrong_text = _first_text(issue, "wrong_text", "wrong_claim", "observed", "actual")
    expected = _first_text(issue, "expected", "expected_text", "correct", "target")
    evidence = _first_text(issue, "evidence", "reason", "statement")
    issue_type = _first_text(issue, "issue_type", "type", default="logic_issue")
    repairability = str(issue.get("repairability") or "").strip().lower()
    missing = []
    if not issue_type:
        missing.append("issue_type")
    if not evidence:
        missing.append("evidence")
    if not wrong_text:
        missing.append("wrong_text_or_wrong_claim")
    if not expected:
        missing.append("expected")

    base = {
        "issue_id": str(issue.get("issue_id") or f"{sample_id}-{index:03d}"),
        "issue_type": issue_type,
        "severity": str(issue.get("severity") or "blocking"),
        "confidence": _float(issue.get("confidence"), default=0.0),
        "evidence": evidence,
        "wrong_text": wrong_text,
        "expected": expected,
        "repairability": repairability or "unspecified",
        "needs_python_verifier": bool(issue.get("needs_python_verifier", False)),
    }
    for optional_key in ("exact_code_before", "exact_code_after"):
        optional_value = _first_text(issue, optional_key)
        if optional_value:
            base[optional_key] = optional_value
    line_replacements = _line_replacements(issue.get("line_replacements"))
    if line_replacements:
        base["line_replacements"] = line_replacements
    if missing:
        return {
            **base,
            "verification_status": "needs_human_review",
            "needs_review_reason": f"missing required verifiable fields: {', '.join(missing)}",
        }
    if repairability and repairability not in REPAIRABLE_VALUES:
        if allow_soft_repair and repairability in SOFT_REPAIRABLE_VALUES and _can_soft_support(base):
            return _soft_supported(base, "repairability requests soft LLM repair")
        return {
            **base,
            "verification_status": "needs_human_review",
            "needs_review_reason": f"repairability is not auto-supported: {repairability}",
        }
    if _requires_deterministic_geometry_contract(base) and issue.get("source") != "deterministic_logic_facts":
        reason = "distance/radius/length text repair requires deterministic geometry contract"
        if allow_soft_repair and _can_soft_support(base):
            return _soft_supported(base, reason)
        return {
            **base,
            "verification_status": "needs_human_review",
            "needs_review_reason": reason,
        }
    return {
        **base,
        "verification_status": "supported",
        "needs_review_reason": "",
    }


def _soft_supported(issue: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **issue,
        "verification_status": "soft_supported",
        "validation_level": "soft_llm",
        "soft_verification_reason": reason,
        "needs_review_reason": "",
    }


def _can_soft_support(issue: dict[str, Any]) -> bool:
    has_replacement_pair = bool(issue.get("wrong_text") and issue.get("expected"))
    has_exact_pair = bool(issue.get("exact_code_before") and issue.get("exact_code_after"))
    has_line_replacements = bool(issue.get("line_replacements"))
    return bool(issue.get("evidence")) and (has_replacement_pair or has_exact_pair or has_line_replacements)


def _first_text(issue: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = issue.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            text = "; ".join(str(item) for item in value if item)
        else:
            text = str(value)
        if text.strip():
            return text.strip()
    return default


def _line_replacements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    replacements = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source_line = _int(item.get("source_line"))
        before = str(item.get("exact_code_before") or "").strip()
        after = str(item.get("exact_code_after") or "").strip()
        if source_line <= 0 or not before or not after:
            continue
        replacements.append(
            {
                "source_line": source_line,
                "exact_code_before": before,
                "exact_code_after": after,
            }
        )
    return replacements


def _requires_deterministic_geometry_contract(issue: dict[str, Any]) -> bool:
    issue_type = str(issue.get("issue_type") or "").lower()
    if any(term in issue_type for term in ("distance", "radius", "length")):
        return True
    evidence = str(issue.get("evidence") or "").lower()
    return any(term in evidence for term in ("distance", "radius", "length"))


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
