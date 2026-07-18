"""Validate a vendor follow-up before platform result aggregation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from .validation import result_violation


def validate_second_result(api: Any, request: Any, first: Any, second: Any) -> Any:
    remaining = request.remaining_tokens - first.tokens_used
    proxy = SimpleNamespace(
        code_path=request.code_path,
        evidence_root=request.evidence_root,
        remaining_tokens=remaining,
    )
    violation = result_violation(second, proxy)
    reason = _reason(violation, first, second)
    if reason is None:
        return second
    return api.RepairResult(
        status="REVIEW_ERROR",
        code_path=request.code_path,
        repairability=getattr(second, "repairability", first.repairability),
        before=dict(first.before),
        after=dict(first.after),
        rounds_used=first.rounds_used + _count(second.rounds_used),
        tokens_used=first.tokens_used + _count(second.tokens_used),
        cost_usd=first.cost_usd + _cost(second.cost_usd),
        evidence_dir=first.evidence_dir,
        reasons=[*first.reasons, reason, *_reasons(second)],
    )


def _reason(violation: str | None, first: Any, second: Any) -> str | None:
    if violation == "vendor_usage_exceeds_remaining_budget":
        return "followup_usage_invalid"
    if violation is not None:
        return f"followup_{violation}"
    if type(second.rounds_used) is not int or not 0 <= second.rounds_used <= 1:
        return "followup_round_count_invalid"
    if dict(second.before) != dict(first.after):
        return "followup_evidence_discontinuity"
    return None


def _count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _cost(value: object) -> float:
    return float(value) if type(value) in {int, float} and value >= 0 else 0.0


def _reasons(result: Any) -> list[str]:
    value = getattr(result, "reasons", [])
    return [str(item) for item in value] if isinstance(value, list) else []
