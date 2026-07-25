"""Independent candidate, render, and certificate binding checks."""

from manim_quality.contracts import (
    PatchScope,
    RevisionCreator,
    RevisionStage,
)

from .certificates import (
    LayoutCertificate,
    LogicCertificate,
    SemanticPreservationCertificate,
)
from .models import (
    ExecutionRequest,
    RenderBinding,
    RenderedCandidate,
    SemanticDecision,
    StageAssessment,
    WarningPolicyDecision,
)
from .revision_models import BoundRevision, CandidateRevision, RepairProposal


def require_proposal(
    value: object, parent: BoundRevision, stage: RevisionStage
) -> CandidateRevision:
    if not isinstance(value, RepairProposal):
        raise TypeError("repair port returned a malformed proposal")
    if value.parent_revision_id != parent.revision_id or value.stage is not stage:
        raise ValueError("repair proposal does not descend from its checkpoint")
    expected_identity = {
        RevisionStage.LOGIC_REPAIR: (
            PatchScope.SCENE_LOGIC,
            RevisionCreator.LOGIC_AGENT,
        ),
        RevisionStage.LAYOUT_REPAIR: (
            PatchScope.LAYOUT_ONLY,
            RevisionCreator.OVERLAP_AGENT,
        ),
    }.get(stage)
    if expected_identity is None:
        raise ValueError("unsupported repair proposal stage")
    if (value.patch_scope, value.created_by) != expected_identity:
        raise ValueError("repair proposal scope or creator does not match its stage")
    return CandidateRevision.from_proposal(value)


def require_rendered(value: object, candidate: CandidateRevision) -> RenderedCandidate:
    if not isinstance(value, RenderedCandidate):
        raise TypeError("renderer returned a malformed candidate result")
    bound = value.revision
    expected = (
        candidate.revision_id,
        candidate.parent_revision_id,
        candidate.code_hash,
        candidate.semantic_fingerprint,
        dict(candidate.scene_hashes),
        candidate.source_code,
    )
    actual = (
        bound.revision_id,
        bound.parent_revision_id,
        bound.code_hash,
        bound.semantic_fingerprint,
        dict(bound.scene_hashes),
        bound.source_code,
    )
    if actual != expected:
        raise ValueError("rendered revision does not bind the proposed source")
    require_binding(bound, value.render)
    return value


def require_binding(revision: BoundRevision, binding: object) -> RenderBinding:
    if not isinstance(binding, RenderBinding):
        raise TypeError("renderer returned a malformed binding")
    expected = (
        revision.revision_id,
        revision.code_hash,
        revision.render_manifest_hash,
        dict(revision.scene_hashes),
    )
    actual = (
        binding.revision_id,
        binding.code_hash,
        binding.render_manifest_hash,
        dict(binding.scene_hashes),
    )
    if actual != expected:
        raise ValueError("render binding does not match the source-bound revision")
    return binding


def require_logic_certificate(
    value: object,
    revision: BoundRevision,
    render: RenderBinding,
    assessment: StageAssessment,
    request: ExecutionRequest,
    warning_policy: WarningPolicyDecision | None,
) -> LogicCertificate:
    if not isinstance(value, LogicCertificate):
        raise TypeError("logic verifier returned a malformed certificate")
    expected = (
        request.job_id,
        revision.revision_id,
        revision.code_hash,
        revision.semantic_fingerprint,
        revision.layout_invariant_fingerprint,
        request.request_hash,
        request.question_hash,
        request.plan_hash,
        request.code_ref,
        request.render_manifest_ref,
        assessment.evidence_hash,
        render.render_manifest_hash,
        render.manifest_evidence_hash,
        request.versions,
        assessment.warnings,
        None if warning_policy is None else warning_policy.evidence_hash,
    )
    actual = tuple(getattr(value, name) for name in value.__dataclass_fields__)
    if actual != expected:
        raise ValueError("logic certificate does not bind independent verification")
    return value


def require_layout_certificate(
    value: object,
    revision: BoundRevision,
    render: RenderBinding,
    logic_checkpoint: BoundRevision,
    assessment: StageAssessment,
    request: ExecutionRequest,
    warning_policy: WarningPolicyDecision | None,
) -> LayoutCertificate:
    if not isinstance(value, LayoutCertificate):
        raise TypeError("layout recheck returned a malformed certificate")
    expected = (
        request.job_id,
        revision.revision_id,
        revision.code_hash,
        render.render_manifest_hash,
        logic_checkpoint.revision_id,
        request.request_hash,
        assessment.evidence_hash,
        render.manifest_evidence_hash,
        0,
        request.versions,
        assessment.warnings,
        None if warning_policy is None else warning_policy.evidence_hash,
    )
    actual = tuple(getattr(value, name) for name in value.__dataclass_fields__)
    if actual != expected:
        raise ValueError("layout certificate does not bind independent recheck")
    return value


def require_semantic_certificate(
    value: object,
    logic_checkpoint: BoundRevision,
    final: BoundRevision,
    request: ExecutionRequest,
    verifier_identity,
) -> SemanticPreservationCertificate:
    if not isinstance(value, SemanticPreservationCertificate):
        raise TypeError("layout semantic verifier returned a malformed certificate")
    expected = (
        request.job_id,
        logic_checkpoint.revision_id,
        logic_checkpoint.code_hash,
        final.revision_id,
        final.code_hash,
        request.request_hash,
        request.question_hash,
        request.plan_hash,
        verifier_identity,
        request.versions.layout_semantic_verifier_version,
        value.evidence_hash,
        SemanticDecision.PRESERVED,
    )
    actual = tuple(getattr(value, name) for name in value.__dataclass_fields__)
    if actual != expected:
        raise ValueError("layout semantic preservation was not independently certified")
    return value
