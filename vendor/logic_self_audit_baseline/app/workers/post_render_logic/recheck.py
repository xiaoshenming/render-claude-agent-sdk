"""Recheck frozen post-render logic issues after a repair attempt."""

from __future__ import annotations

from typing import Any

from app.workers.post_render_logic.schemas import LogicIssue, RecheckReport
from app.workers.post_render_logic.scene_patch import _extract_scene_code


def recheck_issues(code: str, issues: list[LogicIssue]) -> RecheckReport:
    """Only evaluate frozen acceptance predicates; do not scan for new issues."""
    results = [_recheck_issue(code, issue) for issue in issues]
    if not results:
        decision = "unverifiable"
    elif all(result["status"] == "fixed" for result in results):
        decision = "accept_repair"
    else:
        decision = "reject_repair"

    return RecheckReport(
        recheck_id="recheck-frozen-issues",
        checked_issue_ids=[issue.issue_id for issue in issues],
        results=results,
        final_decision=decision,
    )


def _recheck_issue(code: str, issue: LogicIssue) -> dict[str, Any]:
    predicate_results = [
        _eval_predicate(code, predicate)
        for predicate in issue.acceptance_predicates
    ]
    passed = predicate_results and all(item["passed"] for item in predicate_results)
    return {
        "issue_id": issue.issue_id,
        "status": "fixed" if passed else "still_present",
        "confidence": 1.0 if passed else 0.0,
        "predicate_results": predicate_results,
        "scope_compliance": "passed",
    }


def _eval_predicate(code: str, predicate: dict[str, Any]) -> dict[str, Any]:
    kind = predicate.get("predicate")
    value = str(predicate.get("value", ""))
    scene_id = predicate.get("scene_id")
    haystack = _extract_scene_code(code, scene_id) if scene_id else code

    if kind == "text_absent":
        passed = value not in haystack
    elif kind == "text_present":
        passed = value in haystack
    else:
        passed = False

    return {
        "predicate": kind,
        "passed": passed,
        "value": value,
        "scene_id": scene_id,
    }
