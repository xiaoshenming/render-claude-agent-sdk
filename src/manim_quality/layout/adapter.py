"""Platform orchestration boundary for overlap repair candidates."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from .policy import ResidualRiskPolicy, layout_invariant_fingerprint
from .result_mapping import (
    OverlapRepairResult,
    VendorResult,
    error_result,
    map_vendor_result,
)
from .validation import result_violation
from .vendor_runtime import MaterializedQualityRepair
from .timing import TimedChecker


@dataclass(frozen=True, slots=True)
class OverlapRepairRequest:
    job_id: str
    code_path: Path
    layout_context_path: Path
    evidence_root: Path
    remaining_tokens: int

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id must not be empty")
        for path in (self.code_path, self.layout_context_path):
            if not path.is_file():
                raise ValueError(f"required overlap artifact is missing: {path}")
        if type(self.remaining_tokens) is not int or self.remaining_tokens <= 0:
            raise ValueError("remaining_tokens must be a positive integer")


class RepairBackend(Protocol):
    def repair(
        self, request: OverlapRepairRequest, checker: object
    ) -> VendorResult: ...


class OverlapAdapter:
    def __init__(
        self,
        backend: RepairBackend,
        *,
        policy: ResidualRiskPolicy | None = None,
    ) -> None:
        self._backend = backend
        self._policy = policy or ResidualRiskPolicy()

    def repair(
        self, request: OverlapRepairRequest, checker: object
    ) -> OverlapRepairResult:
        started = time.perf_counter()
        timed_checker = TimedChecker(checker)
        try:
            result = self._backend.repair(request, timed_checker)
        except Exception as error:
            mapped = _backend_error(request, "vendor_repair_error", error)
            return _with_timing(mapped, timed_checker, started)
        invalid = result_violation(result, request)
        if invalid is not None:
            mapped = _invalid_result(request, result, invalid)
            return _with_timing(mapped, timed_checker, started)
        try:
            result = self._maybe_second_attempt(request, timed_checker, result)
        except Exception as error:
            mapped = map_vendor_result(
                result,
                original_code_path=request.code_path,
                policy=self._policy,
            )
            mapped = replace(
                mapped,
                reasons=(
                    *mapped.reasons,
                    f"overlap_second_attempt_error:{type(error).__name__}",
                    "previous_best_preserved",
                ),
            )
            return _with_timing(mapped, timed_checker, started)
        invalid = result_violation(result, request)
        if invalid is not None:
            mapped = _invalid_result(request, result, invalid)
            return _with_timing(mapped, timed_checker, started)
        mapped = map_vendor_result(
            result,
            original_code_path=request.code_path,
            policy=self._policy,
        )
        return _with_timing(mapped, timed_checker, started)

    def _maybe_second_attempt(
        self,
        request: OverlapRepairRequest,
        checker: object,
        first: VendorResult,
    ) -> VendorResult:
        remaining = request.remaining_tokens - first.tokens_used
        residual = _blocking(first.after)
        if self._policy.allow_full_candidate_fallback(
            residual_blocking=_blocking(first.after),
            stop_reasons=tuple(first.reasons),
            remaining_tokens=remaining,
            attempts_used=first.rounds_used,
        ):
            fallback = getattr(self._backend, "repair_full_candidate", None)
            return first if fallback is None else fallback(request, checker, first)
        if not self._policy.allow_core_followup(
            before_blocking=_blocking(first.before),
            residual_blocking=residual,
            remaining_tokens=remaining,
            attempts_used=first.rounds_used,
        ) or not _layout_semantics_match(request.code_path, first.code_path):
            return first
        followup = getattr(self._backend, "repair_core_followup", None)
        return first if followup is None else followup(request, checker, first)


def _backend_error(
    request: OverlapRepairRequest,
    prefix: str,
    error: Exception,
    *,
    observed: VendorResult | None = None,
) -> OverlapRepairResult:
    if observed is not None:
        return error_result(
            request.code_path,
            reason=f"{prefix}:{type(error).__name__}",
            vendor_status=getattr(observed, "status", "REVIEW_ERROR"),
            before_blocking=_blocking(observed.before),
            after_blocking=_blocking(observed.after),
            rounds_used=_non_negative_int(observed.rounds_used),
            tokens_used=_non_negative_int(observed.tokens_used),
            cost_usd=_non_negative_cost(observed.cost_usd),
            evidence_dir=_trusted_evidence(
                observed.evidence_dir, request.evidence_root
            ),
        )
    return error_result(
        request.code_path,
        reason=f"{prefix}:{type(error).__name__}",
    )


def _invalid_result(
    request: OverlapRepairRequest, result: VendorResult, reason: str
) -> OverlapRepairResult:
    return error_result(
        request.code_path,
        reason=reason,
        vendor_status=getattr(result, "status", "REVIEW_ERROR"),
        before_blocking=_blocking(result.before),
        after_blocking=_blocking(result.after),
        rounds_used=_non_negative_int(result.rounds_used),
        tokens_used=_non_negative_int(result.tokens_used),
        cost_usd=_non_negative_cost(result.cost_usd),
        evidence_dir=_trusted_evidence(result.evidence_dir, request.evidence_root),
    )


def _blocking(payload: dict[str, object]) -> int:
    value = payload.get("blocking_count", -1)
    return value if type(value) is int else -1


def _non_negative_int(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _non_negative_cost(value: object) -> float:
    return float(value) if type(value) in {int, float} and value >= 0 else 0.0


def _trusted_evidence(path: object, root: Path) -> Path | None:
    try:
        if not isinstance(path, Path) or path.is_symlink() or not path.is_dir():
            return None
        resolved = path.resolve(strict=True)
        allowed = root.resolve()
        return resolved if resolved == allowed or allowed in resolved.parents else None
    except OSError:
        return None


def _layout_semantics_match(original: Path, candidate: Path) -> bool:
    try:
        return layout_invariant_fingerprint(
            original.read_text(encoding="utf-8")
        ) == layout_invariant_fingerprint(candidate.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False


def _with_timing(
    result: OverlapRepairResult, checker: TimedChecker, started: float
) -> OverlapRepairResult:
    elapsed = round((time.perf_counter() - started) * 1_000)
    return replace(result, timing=checker.summary(elapsed))


__all__ = ["MaterializedQualityRepair", "OverlapAdapter", "OverlapRepairRequest"]
