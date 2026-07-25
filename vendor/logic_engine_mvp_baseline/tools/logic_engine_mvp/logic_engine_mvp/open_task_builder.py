from __future__ import annotations

from pathlib import Path
from typing import Any


SCHEMA_VERSION = "logic_engine_mvp.open_repair_task.v1"


def build_open_repair_task(case_dir: Path, review: dict[str, Any]) -> dict[str, Any]:
    case_dir = Path(case_dir)
    sample_id = str(review.get("sample_id") or case_dir.name)
    issues = [
        _task_issue(sample_id, index, issue)
        for index, issue in enumerate(_open_repair_issues(review), start=1)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "sample_id": sample_id,
        "task_type": "open_logic_repair",
        "source": "discarded_llm_issues",
        "issue_count": len(issues),
        "issues": issues,
        "policy": {
            "edit_file": "candidate.py",
            "allowed_tools": ["Read", "Edit"],
            "disallowed_tools": ["Bash", "Write"],
            "no_overlap_repair": True,
            "no_sample_specific_rules": True,
            "minimal_general_edit": True,
        },
        "validation_policy": {
            "requires_render": True,
            "requires_second_review": True,
            "count_as": "open_repair_not_contract_success",
        },
    }


def _open_repair_issues(review: dict[str, Any]) -> list[dict[str, Any]]:
    issues = review.get("discarded_issues")
    if not isinstance(issues, list):
        return []
    return [
        issue
        for issue in issues
        if isinstance(issue, dict) and issue.get("open_repair_candidate") and _is_actionable_open_issue(issue)
    ]


def _is_actionable_open_issue(issue: dict[str, Any]) -> bool:
    evidence = _text(issue.get("evidence"))
    wrong_claim = _text(issue.get("wrong_claim") or issue.get("wrong_text"))
    expected_behavior = _text(issue.get("expected_behavior") or issue.get("expected_text") or issue.get("expected"))
    if not evidence or not wrong_claim or not expected_behavior:
        return False
    if wrong_claim.strip() == expected_behavior.strip():
        return False
    if _string_list(issue.get("missing_fields")):
        return False
    return not _looks_like_no_error_evidence(evidence)


def _looks_like_no_error_evidence(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    no_error_phrases = (
        "no calculation error",
        "no computation error",
        "no logic error",
        "no error found",
        "not a calculation error",
        "is correct",
    )
    return any(phrase in normalized for phrase in no_error_phrases)


def _task_issue(sample_id: str, index: int, issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_id": f"{sample_id}-open-{index:03d}",
        "issue_type": _text(issue.get("issue_type")),
        "evidence": _text(issue.get("evidence")),
        "wrong_claim": _text(issue.get("wrong_claim") or issue.get("wrong_text")),
        "expected_behavior": _text(issue.get("expected_behavior") or issue.get("expected_text")),
        "needs_review_reason": _text(issue.get("needs_review_reason")),
        "missing_fields": _string_list(issue.get("missing_fields")),
        "discarded_reason": _text(issue.get("discarded_reason")),
    }


def _text(value: Any, limit: int = 800) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
