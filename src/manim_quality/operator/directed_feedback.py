"""Convert authoritative Final Assurance findings into Coder input evidence."""

from __future__ import annotations

from collections.abc import Mapping


def directed_reviewer_context(
    feedback: Mapping[str, object],
) -> tuple[dict[str, object], ...] | None:
    if feedback.get("origin") != "final_assurance":
        return None
    issues = feedback.get("issues")
    if not isinstance(issues, list) or not issues:
        return None
    return ({
        "agent_type": "directed_final_assurance_feedback",
        "is_error": False,
        "payload": {
            "decision": "needs_repair",
            "diagnosis": "Use the frozen Final Assurance findings directly.",
            "issues": issues,
        },
        "usage": None,
        "usage_complete": True,
        "model": None,
        "duration_ms": 0,
        "turns": 0,
        "tool_calls": [],
        "reviewers_skipped": True,
        "skip_reason": "authoritative_final_assurance_feedback",
    },)
