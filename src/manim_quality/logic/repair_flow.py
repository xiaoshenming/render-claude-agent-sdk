"""Bounded logic repair loop that produces an unrendered candidate only."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from manim_quality.revisions.fingerprint import code_hash

from ._repair_flow_models import (
    AttemptOutcome,
    AttemptStatus,
    CoderPort,
    LogicRepairFlowResult,
    RepairFlowStatus,
    VerifierPort,
)
from .coder import LogicCoderError
from .candidate_history import CandidateHistory
from .candidate_policy import coder_error_outcome, human_review_result
from .candidate_policy import ready_result, rejected_result
from .repair_plan import RepairPlan


class LogicRepairFlow:
    def __init__(self, coder: CoderPort, verifier: VerifierPort) -> None:
        if not callable(getattr(coder, "patch", None)):
            raise TypeError("coder must provide patch")
        if not callable(getattr(verifier, "verify", None)):
            raise TypeError("verifier must provide verify")
        self._coder = coder
        self._verifier = verifier

    def run(
        self,
        *,
        run_id: str,
        plan: RepairPlan,
        workspace: Path,
        candidate_path: Path,
        coder_estimated_input_tokens: int,
        coder_reserved_output_tokens: int,
        verifier_estimated_input_tokens: int,
        verifier_reserved_output_tokens: int,
    ) -> LogicRepairFlowResult:
        candidate = _candidate_path(workspace, candidate_path)
        baseline = candidate.read_text(encoding="utf-8")
        if code_hash(baseline) != plan.source_code_hash:
            raise ValueError("candidate no longer matches repair plan")
        keep_candidate = False
        try:
            result = self._run_attempts(
                run_id=run_id,
                plan=plan,
                workspace=workspace,
                candidate=candidate,
                baseline=baseline,
                coder_tokens=(
                    coder_estimated_input_tokens,
                    coder_reserved_output_tokens,
                ),
                verifier_tokens=(
                    verifier_estimated_input_tokens,
                    verifier_reserved_output_tokens,
                ),
            )
            keep_candidate = result.status in {
                RepairFlowStatus.CANDIDATE_READY,
                RepairFlowStatus.CANDIDATE_RISK,
            }
            return result
        finally:
            if not keep_candidate:
                candidate.write_text(baseline, encoding="utf-8")

    def _run_attempts(
        self,
        *,
        run_id: str,
        plan: RepairPlan,
        workspace: Path,
        candidate: Path,
        baseline: str,
        coder_tokens: tuple[int, int],
        verifier_tokens: tuple[int, int],
    ) -> LogicRepairFlowResult:
        hashes: list[str] = []
        resolved: tuple[str, ...] = ()
        retry_context: Mapping[str, object] | None = None
        history = CandidateHistory()
        for attempt in range(1, plan.max_attempts + 1):
            outcome = self._attempt(
                run_id=run_id,
                attempt=attempt,
                plan=plan,
                workspace=workspace,
                candidate=candidate,
                baseline=baseline,
                coder_tokens=coder_tokens,
                verifier_tokens=verifier_tokens,
                retry_context=retry_context,
            )
            history.consider(outcome)
            result = _terminal_result(
                outcome, history, candidate, baseline, hashes, attempt, plan.max_attempts
            )
            if result is not None:
                return result
            if outcome.status is AttemptStatus.REJECTED:
                retry_context = {"previous_error": outcome.reason}
                continue
            improvement = outcome.resolved_issue_ids
            if _strict_improvement(resolved, improvement):
                resolved = improvement
            retry_context = _retry_context(plan, outcome)
            candidate.write_text(baseline, encoding="utf-8")
        preserved = history.preserve(
            candidate, hashes, plan.max_attempts, "best candidate preserved"
        )
        return preserved or rejected_result(
            candidate,
            baseline,
            hashes,
            plan.max_attempts,
            "repair attempt limit reached",
        )

    def _attempt(
        self,
        *,
        run_id: str,
        attempt: int,
        plan: RepairPlan,
        workspace: Path,
        candidate: Path,
        baseline: str,
        coder_tokens: tuple[int, int],
        verifier_tokens: tuple[int, int],
        retry_context: Mapping[str, object] | None,
    ) -> AttemptOutcome:
        try:
            patch = self._coder.patch(
                run_id=f"{run_id}-coder-{attempt}",
                plan=plan,
                workspace=workspace,
                candidate_path=candidate,
                estimated_input_tokens=coder_tokens[0],
                reserved_output_tokens=coder_tokens[1],
                retry_context=retry_context,
            )
        except LogicCoderError as error:
            return coder_error_outcome(candidate, baseline, error)
        patch_hash = patch.diff.patch_hash
        if patch.validation.passed:
            return AttemptOutcome(AttemptStatus.READY, patch_hash, patch.candidate_code)
        if not patch.validation.requires_directed_verifier:
            return AttemptOutcome(
                AttemptStatus.REJECTED,
                patch_hash=patch_hash,
                reason="deterministic validation failed",
            )
        deterministic = _deterministically_resolved(plan, patch.validation)
        return self._verify_attempt(
            run_id,
            attempt,
            plan,
            workspace,
            candidate,
            baseline,
            verifier_tokens,
            patch,
            deterministic,
        )

    def _verify_attempt(
        self,
        run_id,
        attempt,
        plan,
        workspace,
        candidate,
        baseline,
        verifier_tokens,
        patch,
        deterministic,
    ) -> AttemptOutcome:
        try:
            verification = self._verifier.verify(
                run_id=f"{run_id}-verifier-{attempt}",
                plan=plan,
                diff=patch.diff,
                validation=patch.validation,
                before_code=baseline,
                workspace=workspace,
                candidate_path=candidate,
                estimated_input_tokens=verifier_tokens[0],
                reserved_output_tokens=verifier_tokens[1],
            )
        except Exception as error:
            return AttemptOutcome(
                AttemptStatus.PARTIAL,
                patch.diff.patch_hash,
                patch.candidate_code,
                deterministic,
                (f"verifier_error: {error}",),
            )
        if verification.verified:
            return AttemptOutcome(
                AttemptStatus.READY, patch.diff.patch_hash, patch.candidate_code
            )
        status = (
            AttemptStatus.HUMAN_REVIEW
            if verification.decision == "human_review"
            else AttemptStatus.PARTIAL
        )
        return AttemptOutcome(
            status,
            patch.diff.patch_hash,
            patch.candidate_code,
            deterministic,
            tuple(verification.review_gaps),
        )


def _terminal_result(
    outcome: AttemptOutcome,
    history: CandidateHistory,
    candidate: Path,
    baseline: str,
    hashes: list[str],
    attempt: int,
    max_attempts: int,
) -> LogicRepairFlowResult | None:
    if outcome.patch_hash in hashes:
        hashes.append(outcome.patch_hash)
        return history.preserve(candidate, hashes, attempt, "duplicate patch") or (
            rejected_result(candidate, baseline, hashes, attempt, "duplicate patch")
        )
    if outcome.patch_hash is not None:
        hashes.append(outcome.patch_hash)
    if outcome.status is AttemptStatus.READY:
        return ready_result(hashes, attempt, outcome.candidate_code or "")
    if outcome.status is AttemptStatus.REJECTED and attempt >= max_attempts:
        return history.preserve(candidate, hashes, attempt, outcome.reason) or (
            rejected_result(candidate, baseline, hashes, attempt, outcome.reason)
        )
    if outcome.status is AttemptStatus.HUMAN_REVIEW:
        reason = "verifier requested human review"
        return history.preserve(candidate, hashes, attempt, reason) or human_review_result(
            candidate, baseline, hashes, attempt, "; ".join(outcome.review_gaps)
        )
    if attempt >= max_attempts:
        reason = "repair attempts ended; best candidate preserved"
        return history.preserve(candidate, hashes, attempt, reason) or rejected_result(
            candidate, baseline, hashes, attempt, "no measurable improvement"
        )
    return None


def _strict_improvement(previous: tuple[str, ...], current: tuple[str, ...]) -> bool:
    return bool(current) and set(previous) < set(current)


def _deterministically_resolved(plan, validation) -> tuple[str, ...]:
    resolved: list[str] = []
    for issue_id in plan.issue_ids:
        checks = [check for check in validation.checks if check.issue_id == issue_id]
        if checks and all(check.status.value == "pass" for check in checks):
            resolved.append(issue_id)
    return tuple(resolved)


def _retry_context(plan: RepairPlan, outcome: AttemptOutcome) -> Mapping[str, object]:
    resolved = outcome.resolved_issue_ids
    return {
        "previous_patch_hash": outcome.patch_hash,
        "resolved_issue_ids": list(resolved),
        "remaining_issue_ids": [
            issue_id for issue_id in plan.issue_ids if issue_id not in resolved
        ],
    }


def _candidate_path(workspace: Path, candidate_path: Path) -> Path:
    root = Path(workspace).resolve(strict=True)
    candidate = Path(candidate_path).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("candidate_path must be a file inside workspace")
    return candidate
