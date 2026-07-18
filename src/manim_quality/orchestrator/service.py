"""Persisted quality flow; the sole owner of checkpoint promotion."""

from manim_quality.contracts import QualityState
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.delivery.gate_models import FinalGateRequest
from manim_quality.revisions.store import (
    CommitFence,
    RepositoryError,
    RevisionRepository,
)

from .delivery_flow import DeliveryCoordinator
from .hold_flow import HoldCoordinator
from .identity import ComponentIdentity, ComponentRole
from .models import ExecutionRequest, OrchestrationResult
from .port_validation import require_orchestration_ports
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
from .revision_models import BoundRevision
from .stages import StageCoordinator
from .transitions import event_hash, transition


class QualityOrchestrator:
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
        gate: FinalConsistencyGate,
    ) -> None:
        require_orchestration_ports(
            logic_review,
            logic_repair,
            logic_verify,
            layout_detect,
            layout_repair,
            layout_recheck,
            layout_semantic_verify,
            warning_policy,
            renderer,
        )
        _require_component_separation(
            logic_repair,
            logic_verify,
            layout_repair,
            layout_recheck,
            layout_semantic_verify,
        )
        self._repository = repository
        self._gate = gate
        self._semantic_verifier_identity = layout_semantic_verify.identity
        self._delivery = DeliveryCoordinator(repository)
        self._holds = HoldCoordinator(repository)
        self._stages = StageCoordinator(
            repository,
            logic_review,
            logic_repair,
            logic_verify,
            layout_detect,
            layout_repair,
            layout_recheck,
            layout_semantic_verify,
            warning_policy,
            renderer,
        )

    def execute(
        self,
        request: ExecutionRequest,
        *,
        commit_fence: CommitFence | None = None,
    ) -> OrchestrationResult:
        self._repository.begin_run(request.job_id, request.run_id, request.request_hash)
        existing = self._repository.get_run_result(
            request.job_id, request.run_id, request.request_hash
        )
        if existing is not None:
            return OrchestrationResult(
                existing, self._repository.get_job(request.job_id)
            )
        try:
            return self._execute(request, commit_fence)
        except RepositoryError:
            raise
        except Exception as error:
            return self._holds.hold(request, error, commit_fence)

    def _execute(
        self, request: ExecutionRequest, commit_fence: CommitFence | None
    ) -> OrchestrationResult:
        snapshot = self._repository.get_job(request.job_id)
        baseline = self._repository.get_revision(snapshot.render_baseline_revision_id)
        revision = BoundRevision(baseline, request.source_code)
        snapshot = transition(
            self._repository,
            snapshot,
            QualityState.LOGIC_REVIEWING,
            request.run_id,
            "logic_review_started",
            event_hash("logic", revision.code_hash),
        )
        assessment = self._stages.assess_logic(revision, request)
        revision, render, logic, warnings, policies, snapshot = self._stages.logic(
            request, revision, assessment, snapshot
        )
        logic_checkpoint = revision
        snapshot = transition(
            self._repository,
            snapshot,
            QualityState.LAYOUT_CHECKING,
            request.run_id,
            "layout_check_started",
            logic.hash,
        )
        assessment = self._stages.assess_layout(revision, request)
        layout_result = self._stages.layout(
            request, revision, render, logic_checkpoint, assessment, snapshot
        )
        (
            revision,
            render,
            layout,
            semantic,
            new_warnings,
            new_policies,
            snapshot,
        ) = layout_result
        gate_request = self._final_gate_request(
            request,
            snapshot,
            revision,
            logic_checkpoint,
            render,
            logic,
            layout,
            semantic,
            warnings + new_warnings,
            policies + new_policies,
        )
        gate = self._gate.evaluate(gate_request)
        if not gate.passed:
            raise ValueError("final_gate:" + ",".join(gate.failures))
        return self._delivery.deliver(gate_request, gate, commit_fence)

    def _final_gate_request(
        self,
        request,
        snapshot,
        revision,
        logic_checkpoint,
        render,
        logic,
        layout,
        semantic,
        warnings,
        policies,
    ) -> FinalGateRequest:
        snapshot = transition(
            self._repository,
            snapshot,
            QualityState.FINAL_CONSISTENCY_GATE,
            request.run_id,
            "final_gate_started",
            layout.hash,
        )
        render = self._stages.bind(revision, request)
        return FinalGateRequest(
            request,
            snapshot,
            revision,
            logic_checkpoint,
            render,
            logic,
            layout,
            semantic,
            self._semantic_verifier_identity,
            request.versions,
            warnings,
            policies,
        )


def _require_component_separation(
    logic_repair,
    logic_verify,
    layout_repair,
    layout_recheck,
    layout_semantic_verify,
) -> None:
    if logic_repair is logic_verify:
        raise ValueError("logic repair and verifier must be distinct components")
    if layout_repair is layout_recheck:
        raise ValueError("layout repair and recheck must be distinct components")
    if layout_repair is layout_semantic_verify:
        raise ValueError(
            "layout repair and semantic verifier must be distinct components"
        )
    if layout_recheck is layout_semantic_verify:
        raise ValueError(
            "layout recheck and semantic verifier must be distinct components"
        )
    declared = (
        (logic_repair, ComponentRole.LOGIC_REPAIR),
        (logic_verify, ComponentRole.LOGIC_VERIFY),
        (layout_repair, ComponentRole.LAYOUT_REPAIR),
        (layout_recheck, ComponentRole.LAYOUT_RECHECK),
        (layout_semantic_verify, ComponentRole.LAYOUT_SEMANTIC_VERIFY),
    )
    identities = [_require_identity(component, role) for component, role in declared]
    _require_unique_identity_field(identities, "component_id")
    _require_unique_identity_field(identities, "session_scope")


def _require_identity(component, role: ComponentRole) -> ComponentIdentity:
    identity = getattr(component, "identity", None)
    if not isinstance(identity, ComponentIdentity):
        raise TypeError(f"{role.value} component requires ComponentIdentity")
    if identity.role is not role:
        raise ValueError(
            f"component {identity.component_id} expected role {role.value}, "
            f"got {identity.role.value}"
        )
    return identity


def _require_unique_identity_field(
    identities: list[ComponentIdentity], field_name: str
) -> None:
    values = [getattr(identity, field_name) for identity in identities]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {field_name} across independent components")
