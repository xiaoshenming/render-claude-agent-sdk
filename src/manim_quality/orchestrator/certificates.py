"""Independent stage certificate envelopes."""

from dataclasses import dataclass

from manim_quality.delivery.evidence import content_hash

from ._model_validation import require_hash, require_text
from .identity import ComponentIdentity, ComponentRole
from .models import SemanticDecision, VersionBindings, WarningRecord


@dataclass(frozen=True, slots=True)
class LogicCertificate:
    job_id: str
    revision_id: str
    code_hash: str
    semantic_fingerprint: str
    layout_invariant_fingerprint: str
    request_hash: str
    question_hash: str
    plan_hash: str
    code_ref: str
    render_manifest_ref: str
    assessment_hash: str
    render_manifest_hash: str
    render_evidence_hash: str
    versions: VersionBindings
    warnings: tuple[WarningRecord, ...] = ()
    warning_policy_hash: str | None = None

    @property
    def hash(self) -> str:
        return content_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "assessment_hash": self.assessment_hash,
            "code_hash": self.code_hash,
            "code_ref": self.code_ref,
            "job_id": self.job_id,
            "layout_invariant_fingerprint": self.layout_invariant_fingerprint,
            "plan_hash": self.plan_hash,
            "question_hash": self.question_hash,
            "render_evidence_hash": self.render_evidence_hash,
            "render_manifest_hash": self.render_manifest_hash,
            "render_manifest_ref": self.render_manifest_ref,
            "request_hash": self.request_hash,
            "revision_id": self.revision_id,
            "semantic_fingerprint": self.semantic_fingerprint,
            "versions": self.versions.to_dict(),
            "warning_policy_hash": self.warning_policy_hash,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class LayoutCertificate:
    job_id: str
    revision_id: str
    code_hash: str
    render_manifest_hash: str
    logic_checkpoint_revision_id: str
    request_hash: str
    assessment_hash: str
    render_evidence_hash: str
    blocking_issues: int
    versions: VersionBindings
    warnings: tuple[WarningRecord, ...] = ()
    warning_policy_hash: str | None = None

    @property
    def hash(self) -> str:
        return content_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "assessment_hash": self.assessment_hash,
            "blocking_issues": self.blocking_issues,
            "code_hash": self.code_hash,
            "job_id": self.job_id,
            "logic_checkpoint_revision_id": self.logic_checkpoint_revision_id,
            "render_evidence_hash": self.render_evidence_hash,
            "render_manifest_hash": self.render_manifest_hash,
            "request_hash": self.request_hash,
            "revision_id": self.revision_id,
            "versions": self.versions.to_dict(),
            "warning_policy_hash": self.warning_policy_hash,
            "warnings": [item.to_dict() for item in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class SemanticPreservationCertificate:
    job_id: str
    logic_revision_id: str
    logic_code_hash: str
    final_revision_id: str
    final_code_hash: str
    request_hash: str
    question_hash: str
    plan_hash: str
    verifier_identity: ComponentIdentity
    verifier_version: str
    evidence_hash: str
    decision: SemanticDecision

    def __post_init__(self) -> None:
        for name in ("job_id", "logic_revision_id", "final_revision_id"):
            require_text(getattr(self, name), name)
        for name in (
            "logic_code_hash",
            "final_code_hash",
            "request_hash",
            "question_hash",
            "plan_hash",
            "evidence_hash",
        ):
            require_hash(getattr(self, name), name)
        if not isinstance(self.verifier_identity, ComponentIdentity):
            raise TypeError("verifier_identity must be a ComponentIdentity")
        if self.verifier_identity.role is not ComponentRole.LAYOUT_SEMANTIC_VERIFY:
            raise ValueError("verifier_identity must have LAYOUT_SEMANTIC_VERIFY role")
        require_text(self.verifier_version, "verifier_version")
        if not isinstance(self.decision, SemanticDecision):
            raise TypeError("decision must be a SemanticDecision")

    @property
    def hash(self) -> str:
        return content_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "evidence_hash": self.evidence_hash,
            "final_code_hash": self.final_code_hash,
            "final_revision_id": self.final_revision_id,
            "job_id": self.job_id,
            "logic_code_hash": self.logic_code_hash,
            "logic_revision_id": self.logic_revision_id,
            "plan_hash": self.plan_hash,
            "question_hash": self.question_hash,
            "request_hash": self.request_hash,
            "verifier_identity": self.verifier_identity.to_dict(),
            "verifier_version": self.verifier_version,
        }
