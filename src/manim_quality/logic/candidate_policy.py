"""Fail-open outcomes for preserving AI logic candidates and their risks."""

from __future__ import annotations

from pathlib import Path

from manim_quality.revisions.fingerprint import code_hash

from ._repair_flow_models import (
    AttemptOutcome,
    AttemptStatus,
    LogicRepairFlowResult,
    RepairFlowStatus,
)


def coder_error_outcome(
    candidate: Path, baseline: str, error: Exception
) -> AttemptOutcome:
    """Preserve an edit already written before the SDK reported an error."""
    edited = candidate.read_text(encoding="utf-8")
    if edited == baseline:
        return AttemptOutcome(AttemptStatus.REJECTED, reason=str(error))
    return AttemptOutcome(
        AttemptStatus.PARTIAL,
        code_hash(edited),
        edited,
        (),
        (f"coder_error_after_edit: {error}",),
    )


def ready_result(
    hashes: list[str], attempt_count: int, candidate_code: str
) -> LogicRepairFlowResult:
    return LogicRepairFlowResult(
        RepairFlowStatus.CANDIDATE_READY,
        attempt_count,
        tuple(hashes),
        candidate_code,
        True,
        "candidate requires external render and recheck",
    )


def risk_result(
    candidate: Path,
    hashes: list[str],
    attempt_count: int,
    candidate_code: str,
    reason: str,
) -> LogicRepairFlowResult:
    """Keep a runnable patch when verification is uncertain, with evidence."""
    candidate.write_text(candidate_code, encoding="utf-8")
    return LogicRepairFlowResult(
        RepairFlowStatus.CANDIDATE_RISK,
        attempt_count,
        tuple(hashes),
        candidate_code,
        True,
        reason or "candidate preserved with unresolved verifier risk",
    )


def rejected_result(
    candidate: Path,
    baseline: str,
    hashes: list[str],
    attempt_count: int,
    reason: str,
) -> LogicRepairFlowResult:
    """Reject only when no usable candidate exists or deterministic checks fail."""
    candidate.write_text(baseline, encoding="utf-8")
    return LogicRepairFlowResult(
        RepairFlowStatus.REJECTED,
        attempt_count,
        tuple(hashes),
        None,
        False,
        reason,
    )


def human_review_result(
    candidate: Path,
    baseline: str,
    hashes: list[str],
    attempt_count: int,
    reason: str,
) -> LogicRepairFlowResult:
    candidate.write_text(baseline, encoding="utf-8")
    return LogicRepairFlowResult(
        RepairFlowStatus.HUMAN_REVIEW,
        attempt_count,
        tuple(hashes),
        None,
        False,
        reason or "directed verifier requested review",
    )
