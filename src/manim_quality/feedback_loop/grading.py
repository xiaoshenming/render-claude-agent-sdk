from __future__ import annotations

from collections.abc import Mapping, Sequence

GRADE_POLICY_VERSION = "final-assurance-grade-v1"


def grade_assurance_row(row: Mapping[str, object]) -> str:
    if row.get("agent_error"):
        return "E"
    agent = row.get("agent")
    if not isinstance(agent, Mapping) or agent.get("status") == "incomplete":
        return "E"
    issues = agent.get("issues")
    rows = (
        [item for item in issues if isinstance(item, Mapping)]
        if _sequence(issues)
        else []
    )
    severities = {str(item.get("severity", "")).lower() for item in rows}
    if severities & {"critical", "blocking", "high"}:
        return "D"
    if "medium" in severities:
        return "C"
    if rows or agent.get("status") == "review":
        return "B"
    return "A"


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
