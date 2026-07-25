"""Atomic accepted delivery construction and persistence."""

from manim_quality.contracts import DeliveryDecision, QualityResult, QualityState
from manim_quality.delivery.certificate import build_certificate
from manim_quality.delivery.gate_models import FinalGateRequest, FinalGateResult
from manim_quality.revisions.store import (
    CommitFence,
    RevisionRepository,
    StaleWrite,
    TransitionEvidence,
)

from .models import OrchestrationResult


class DeliveryCoordinator:
    def __init__(self, repository: RevisionRepository) -> None:
        self._repository = repository

    def deliver(
        self,
        request: FinalGateRequest,
        gate: FinalGateResult,
        commit_fence: CommitFence | None = None,
    ) -> OrchestrationResult:
        execution = request.execution
        latest = self._repository.get_job(execution.job_id)
        if latest != request.snapshot or latest.version != gate.snapshot_version:
            raise StaleWrite(execution.job_id, gate.snapshot_version, latest.version)
        decision = (
            DeliveryDecision.ACCEPT_WITH_WARNING
            if request.warnings
            else DeliveryDecision.ACCEPT
        )
        certificate = build_certificate(
            execution,
            request.snapshot,
            request.final_revision,
            request.render,
            request.logic,
            request.layout,
            request.semantic_preservation,
            gate,
            request.warnings,
            request.warning_decisions,
            request.versions,
            decision,
        )
        final = request.final_revision
        result = _quality_result(request, certificate.hash, decision)
        target = (
            QualityState.ACCEPTED_WITH_WARNING
            if request.warnings
            else QualityState.ACCEPTED
        )
        snapshot = self._repository.finalize_delivery(
            execution.job_id,
            final.revision_id,
            target,
            TransitionEvidence(
                f"{execution.run_id}:delivery_finalized",
                "delivery_finalized",
                certificate.hash,
            ),
            certificate.payload,
            result,
            run_id=execution.run_id,
            request_hash=execution.request_hash,
            expected_version=request.snapshot.version,
            commit_fence=commit_fence,
        )
        return OrchestrationResult(result, snapshot)


def _quality_result(
    request: FinalGateRequest,
    certificate_hash: str,
    decision: DeliveryDecision,
) -> QualityResult:
    final = request.final_revision
    return QualityResult(
        request.execution.job_id,
        decision,
        final.revision_id,
        f"content://{final.code_hash}",
        f"content://{final.render_manifest_hash}",
        f"evidence://{certificate_hash}",
        tuple(item.message for item in request.warnings),
        {},
        {},
    )
