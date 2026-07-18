"""Narrow, independent capabilities injected into quality orchestration."""

from typing import Protocol

from .certificates import (
    LayoutCertificate,
    LogicCertificate,
    SemanticPreservationCertificate,
)
from .identity import ComponentIdentity
from .models import (
    ExecutionRequest,
    RenderBinding,
    RenderedCandidate,
    StageAssessment,
    WarningPolicyDecision,
    WarningRecord,
    WarningStage,
)
from .revision_models import BoundRevision, CandidateRevision, RepairProposal


class LogicReviewPort(Protocol):
    def assess(
        self, revision: BoundRevision, request: ExecutionRequest
    ) -> StageAssessment: ...


class LogicRepairPort(Protocol):
    @property
    def identity(self) -> ComponentIdentity: ...

    def propose(
        self,
        parent: BoundRevision,
        assessment: StageAssessment,
        request: ExecutionRequest,
    ) -> RepairProposal: ...


class LogicVerificationPort(Protocol):
    @property
    def identity(self) -> ComponentIdentity: ...

    def verify(
        self,
        candidate: BoundRevision,
        render: RenderBinding,
        assessment: StageAssessment,
        request: ExecutionRequest,
        warning_policy: WarningPolicyDecision | None,
    ) -> LogicCertificate: ...


class LayoutDetectionPort(Protocol):
    def assess(
        self, revision: BoundRevision, request: ExecutionRequest
    ) -> StageAssessment: ...


class LayoutRepairPort(Protocol):
    @property
    def identity(self) -> ComponentIdentity: ...

    def propose(
        self,
        parent: BoundRevision,
        assessment: StageAssessment,
        request: ExecutionRequest,
    ) -> RepairProposal: ...


class LayoutRecheckPort(Protocol):
    @property
    def identity(self) -> ComponentIdentity: ...

    def verify(
        self,
        candidate: BoundRevision,
        render: RenderBinding,
        assessment: StageAssessment,
        logic_checkpoint: BoundRevision,
        request: ExecutionRequest,
        warning_policy: WarningPolicyDecision | None,
    ) -> LayoutCertificate: ...


class LayoutSemanticVerificationPort(Protocol):
    @property
    def identity(self) -> ComponentIdentity: ...

    def verify(
        self,
        logic_checkpoint: BoundRevision,
        final: BoundRevision,
        render: RenderBinding,
        assessment: StageAssessment,
        request: ExecutionRequest,
    ) -> SemanticPreservationCertificate: ...


class WarningPolicyPort(Protocol):
    def authorize(
        self,
        stage: WarningStage,
        warnings: tuple[WarningRecord, ...],
        assessment_hash: str,
        request: ExecutionRequest,
    ) -> WarningPolicyDecision: ...


class RenderStage(Protocol):
    def render(
        self, candidate: CandidateRevision, request: ExecutionRequest
    ) -> RenderedCandidate: ...

    def bind(
        self, revision: BoundRevision, request: ExecutionRequest
    ) -> RenderBinding: ...
