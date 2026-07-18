"""Immutable input and output contracts for the deterministic final gate."""

from dataclasses import dataclass

from manim_quality.orchestrator.certificates import (
    LayoutCertificate,
    LogicCertificate,
    SemanticPreservationCertificate,
)
from manim_quality.orchestrator.identity import ComponentIdentity
from manim_quality.orchestrator.models import (
    ExecutionRequest,
    RenderBinding,
    VersionBindings,
    WarningPolicyDecision,
    WarningRecord,
)
from manim_quality.orchestrator.revision_models import BoundRevision
from manim_quality.revisions.store import QualityJobSnapshot


@dataclass(frozen=True, slots=True)
class FinalGateRequest:
    execution: ExecutionRequest
    snapshot: QualityJobSnapshot
    final_revision: BoundRevision
    logic_checkpoint: BoundRevision
    render: RenderBinding
    logic: LogicCertificate
    layout: LayoutCertificate
    semantic_preservation: SemanticPreservationCertificate | None
    semantic_verifier_identity: ComponentIdentity
    versions: VersionBindings
    warnings: tuple[WarningRecord, ...]
    warning_decisions: tuple[WarningPolicyDecision, ...]


@dataclass(frozen=True, slots=True)
class FinalGateResult:
    passed: bool
    failures: tuple[str, ...]
    evidence_hash: str
    snapshot_version: int
    gate_version: str
