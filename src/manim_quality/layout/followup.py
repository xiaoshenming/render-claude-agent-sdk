"""One strict-progress Core follow-up through the vendor public API."""

from __future__ import annotations

from typing import Any

from .policy import agent_token_cap
from .second_attempt import validate_second_result


def execute_core_followup(
    api: Any,
    request: Any,
    checker: Any,
    first: Any,
) -> Any:
    remaining = request.remaining_tokens - first.tokens_used
    budget = api.Budget(
        max_rounds=1,
        token_hard_cap=agent_token_cap(remaining),
        no_progress_stop=1,
        same_signature_stop=2,
        accept_degraded_max_blocking=2,
        accept_degraded_min_reduction_ratio=0.5,
        accept_risk_only_max_blocking=6,
    )
    bundle = api.RepairBundle(
        job_id=f"{request.job_id}-core-followup",
        code_path=first.code_path,
        candidate_mode="core",
        layout_context=request.layout_context_path,
        budget=budget,
        evidence_root=request.evidence_root,
    )
    second = api.repair(bundle, api.ToolBox(checker=checker))
    second = validate_second_result(api, request, first, second)
    if second.status == "REVIEW_ERROR":
        return second
    return _combine(api, request, first, second)


def _combine(api: Any, request: Any, first: Any, second: Any) -> Any:
    improved = second.status in {"SUCCESS_CLEAN", "SUCCESS_DEGRADED"} and _blocking(
        second.after
    ) < _blocking(first.after)
    reasons = [*first.reasons, "core_followup", *second.reasons]
    result = api.RepairResult(
        status=second.status if improved else "REPAIR_UNCHANGED",
        code_path=second.code_path if improved else request.code_path,
        repairability=second.repairability,
        before=dict(first.before),
        after=dict(second.after) if improved else dict(first.after),
        rounds_used=first.rounds_used + second.rounds_used,
        tokens_used=first.tokens_used + second.tokens_used,
        cost_usd=first.cost_usd + second.cost_usd,
        evidence_dir=second.evidence_dir,
        reasons=reasons,
    )
    return result


def _blocking(payload: dict[str, object]) -> int:
    value = payload.get("blocking_count", -1)
    return value if type(value) is int else -1
