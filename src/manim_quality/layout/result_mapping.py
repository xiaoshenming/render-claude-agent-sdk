"""Fail-closed mapping from vendor evidence to platform overlap candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .policy import ResidualRiskPolicy, layout_invariant_fingerprint


class OverlapDisposition(StrEnum):
    NO_CHANGE = "no_change"
    CANDIDATE_RECHECK_REQUIRED = "candidate_recheck_required"
    RESIDUAL_CANDIDATE_RECHECK_REQUIRED = "residual_candidate_recheck_required"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class OverlapRepairResult:
    disposition: OverlapDisposition
    code_path: Path
    vendor_status: str
    before_blocking: int
    after_blocking: int
    rounds_used: int
    tokens_used: int
    cost_usd: float
    evidence_dir: Path | None
    reasons: tuple[str, ...]
    requires_external_render_recheck: bool


class VendorResult(Protocol):
    status: str
    code_path: Path
    before: dict[str, object]
    after: dict[str, object]
    rounds_used: int
    tokens_used: int
    cost_usd: float
    evidence_dir: Path | None
    reasons: list[str]


def map_vendor_result(
    result: VendorResult,
    *,
    original_code_path: Path,
    policy: ResidualRiskPolicy,
) -> OverlapRepairResult:
    before = _blocking(result.before)
    after = _blocking(result.after)
    reasons = tuple(result.reasons)
    disposition = _disposition(result.status, before, after, policy)
    code_path = result.code_path
    if disposition in _CANDIDATE_DISPOSITIONS:
        disposition, code_path, reasons = _guard_semantics(
            disposition, original_code_path, code_path, reasons
        )
    elif disposition in {OverlapDisposition.REJECTED, OverlapDisposition.ERROR}:
        code_path = original_code_path
    return OverlapRepairResult(
        disposition=disposition,
        code_path=code_path,
        vendor_status=result.status,
        before_blocking=before,
        after_blocking=after,
        rounds_used=result.rounds_used,
        tokens_used=result.tokens_used,
        cost_usd=result.cost_usd,
        evidence_dir=result.evidence_dir,
        reasons=reasons,
        requires_external_render_recheck=disposition in _CANDIDATE_DISPOSITIONS,
    )


def error_result(
    original_code_path: Path,
    *,
    reason: str,
    vendor_status: str = "REVIEW_ERROR",
    before_blocking: int = -1,
    after_blocking: int = -1,
    rounds_used: int = 0,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
    evidence_dir: Path | None = None,
) -> OverlapRepairResult:
    return OverlapRepairResult(
        disposition=OverlapDisposition.ERROR,
        code_path=original_code_path,
        vendor_status=vendor_status,
        before_blocking=before_blocking,
        after_blocking=after_blocking,
        rounds_used=rounds_used,
        tokens_used=tokens_used,
        cost_usd=cost_usd,
        evidence_dir=evidence_dir,
        reasons=(reason,),
        requires_external_render_recheck=False,
    )


_CANDIDATE_DISPOSITIONS = frozenset(
    {
        OverlapDisposition.CANDIDATE_RECHECK_REQUIRED,
        OverlapDisposition.RESIDUAL_CANDIDATE_RECHECK_REQUIRED,
    }
)


def _disposition(
    status: str, before: int, after: int, policy: ResidualRiskPolicy
) -> OverlapDisposition:
    if status == "SUCCESS_CLEAN" and before > 0 and after == 0:
        return OverlapDisposition.CANDIDATE_RECHECK_REQUIRED
    if status == "SUCCESS_DEGRADED" and policy.accepts_degraded(
        before=before, after=after
    ):
        return OverlapDisposition.RESIDUAL_CANDIDATE_RECHECK_REQUIRED
    if status == "REPAIR_UNCHANGED" and before == 0:
        return OverlapDisposition.NO_CHANGE
    if status == "REVIEW_ERROR":
        return OverlapDisposition.ERROR
    return OverlapDisposition.REJECTED


def _guard_semantics(
    disposition: OverlapDisposition,
    original_path: Path,
    candidate_path: Path,
    reasons: tuple[str, ...],
) -> tuple[OverlapDisposition, Path, tuple[str, ...]]:
    try:
        original = original_path.read_text(encoding="utf-8")
        candidate = candidate_path.read_text(encoding="utf-8")
        unchanged = layout_invariant_fingerprint(
            original
        ) == layout_invariant_fingerprint(candidate)
    except (OSError, SyntaxError):
        unchanged = False
    if unchanged:
        return disposition, candidate_path, reasons
    return (
        OverlapDisposition.REJECTED,
        original_path,
        (*reasons, "semantic_fingerprint_changed"),
    )


def _blocking(payload: dict[str, object]) -> int:
    value = payload.get("blocking_count", -1)
    return value if type(value) is int else -1
