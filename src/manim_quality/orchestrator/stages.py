"""Independent assess, repair, render, verify, and policy coordination."""

from manim_quality.contracts import QualityState, RevisionStage
from manim_quality.revisions.store import (
    Checkpoint,
    RevisionRepository,
)

from .checkpoints import (
    require_binding,
    require_logic_certificate,
)
from .failures import StageExecutionError
from .models import (
    RenderBinding,
    StageAction,
    StageAssessment,
    WarningPolicyDecision,
    WarningStage,
)
from .ports import (
    LayoutDetectionPort,
    LayoutRecheckPort,
    LayoutRepairPort,
    LayoutSemanticVerificationPort,
    LogicRepairPort,
    LogicReviewPort,
    LogicVerificationPort,
    RenderStage,
    WarningPolicyPort,
)
from .repair_flow import RepairCoordinator
from .revision_models import BoundRevision
from .stage_verification import verify_layout, verify_semantic
from .transitions import certify, transition


class StageCoordinator:
    def __init__(
        self,
        repository: RevisionRepository,
        logic_review: LogicReviewPort,
        logic_repair: LogicRepairPort,
        logic_verify: LogicVerificationPort,
        layout_detect: LayoutDetectionPort,
        layout_repair: LayoutRepairPort,
        layout_recheck: LayoutRecheckPort,
        layout_semantic_verify: LayoutSemanticVerificationPort,
        warning_policy: WarningPolicyPort,
        renderer: RenderStage,
    ) -> None:
        self._repository = repository
        self._logic_review = logic_review
        self._logic_repair = logic_repair
        self._logic_verify = logic_verify
        self._layout_detect = layout_detect
        self._layout_repair = layout_repair
        self._layout_recheck = layout_recheck
        self._layout_semantic_verify = layout_semantic_verify
        self._warning_policy = warning_policy
        self._renderer = renderer
        self._repairs = RepairCoordinator(
            repository, logic_repair, layout_repair, renderer
        )

    def assess_logic(self, revision, request) -> StageAssessment:
        return _assessment(self._logic_review.assess(revision, request), "logic")

    def assess_layout(self, revision, request) -> StageAssessment:
        return _assessment(self._layout_detect.assess(revision, request), "layout")

    def logic(self, request, revision, assessment, snapshot):
        render = self.bind(revision, request)
        if assessment.action is StageAction.HOLD:
            raise ValueError("logic requested hold")
        policy = None
        if assessment.action is StageAction.WARNING:
            snapshot = transition(
                self._repository,
                snapshot,
                QualityState.POLICY_EVALUATING,
                request.run_id,
                "logic_warning_policy",
                assessment.evidence_hash,
            )
            policy = self._authorize(WarningStage.LOGIC, assessment, request)
        if assessment.action is StageAction.REPAIR:
            snapshot, revision, render = self._repairs.repair(
                request, revision, assessment, snapshot, RevisionStage.LOGIC_REPAIR
            )
        try:
            raw_certificate = self._logic_verify.verify(
                revision, render, assessment, request, policy
            )
            certificate = require_logic_certificate(
                raw_certificate, revision, render, assessment, request, policy
            )
        except Exception as error:
            raise StageExecutionError(
                "logic_verification_error", str(error), revision.revision_id
            ) from error
        target = (
            QualityState.LOGIC_CERTIFIED_WITH_WARNING
            if assessment.warnings
            else QualityState.LOGIC_CERTIFIED
        )
        snapshot = certify(
            self._repository,
            snapshot,
            Checkpoint.LOGIC_CERTIFIED,
            revision.revision_id,
            target,
            request.run_id,
            "logic_certified",
            certificate.hash,
        )
        policies = () if policy is None else (policy,)
        return revision, render, certificate, assessment.warnings, policies, snapshot

    def layout(self, request, revision, render, logic_checkpoint, assessment, snapshot):
        if assessment.action is StageAction.HOLD:
            raise ValueError("layout requested hold")
        policy = None
        if assessment.action is StageAction.WARNING:
            policy = self._authorize(WarningStage.LAYOUT, assessment, request)
        if assessment.action is StageAction.REPAIR:
            snapshot, revision, render = self._repairs.repair(
                request, revision, assessment, snapshot, RevisionStage.LAYOUT_REPAIR
            )
        certificate = verify_layout(
            self._layout_recheck,
            revision,
            render,
            logic_checkpoint,
            assessment,
            request,
            policy,
        )
        semantic = verify_semantic(
            self._layout_semantic_verify,
            logic_checkpoint,
            revision,
            render,
            assessment,
            request,
        )
        target = (
            QualityState.LAYOUT_CERTIFIED_WITH_WARNING
            if assessment.warnings
            else QualityState.LAYOUT_CERTIFIED
        )
        snapshot = certify(
            self._repository,
            snapshot,
            Checkpoint.LAYOUT_CERTIFIED,
            revision.revision_id,
            target,
            request.run_id,
            "layout_certified",
            certificate.hash,
        )
        policies = () if policy is None else (policy,)
        return (
            revision,
            render,
            certificate,
            semantic,
            assessment.warnings,
            policies,
            snapshot,
        )

    def bind(self, revision: BoundRevision, request) -> RenderBinding:
        try:
            result = self._renderer.bind(revision, request)
        except Exception as error:
            raise StageExecutionError("render_error", str(error)) from error
        return require_binding(revision, result)

    def _authorize(self, stage, assessment, request) -> WarningPolicyDecision:
        decision = self._warning_policy.authorize(
            stage, assessment.warnings, assessment.evidence_hash, request
        )
        if not isinstance(decision, WarningPolicyDecision):
            raise TypeError("warning policy returned a malformed decision")
        expected = tuple(item.evidence_hash for item in assessment.warnings)
        if (
            not decision.authorized
            or decision.stage is not stage
            or decision.warning_evidence_hashes != expected
            or decision.policy_version != request.versions.warning_policy_version
        ):
            raise ValueError("warning policy did not authorize exact warning evidence")
        return decision


def _assessment(value: object, stage: str) -> StageAssessment:
    if not isinstance(value, StageAssessment):
        raise TypeError(f"{stage} stage returned a malformed assessment")
    return value
