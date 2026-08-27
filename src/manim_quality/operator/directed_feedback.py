"""Reuse authoritative Final Assurance issues as direct Coder input."""

from __future__ import annotations

from collections.abc import Mapping


def directed_reviewer_context(
    feedback: Mapping[str, object],
) -> tuple[dict[str, object], ...] | None:
    if feedback.get("origin") != "final_assurance":
        return None
    issues = feedback.get("issues")
    issues = issues if isinstance(issues, list) else []
    brief = feedback.get("repair_brief")
    brief = brief if isinstance(brief, Mapping) else {}
    diagnosis = str(
        brief.get("coder_text")
        or "Use the frozen Final Assurance findings directly."
    )
    return ({
        "agent_type": "directed_final_assurance_feedback",
        "is_error": False,
        "payload": {
            "decision": "needs_repair",
            "diagnosis": diagnosis,
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
