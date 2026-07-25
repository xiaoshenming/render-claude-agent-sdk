"""Immutable public models exchanged across orchestration ports."""

from dataclasses import dataclass
from enum import StrEnum

from manim_quality.contracts import QualityResult
from manim_quality.revisions.store import QualityJobSnapshot

from ._model_validation import require_hash, require_text
from .render_models import RenderBinding as RenderBinding
from .render_models import RenderedCandidate as RenderedCandidate
from .revision_models import BoundRevision as BoundRevision
from .versioning import AgentIdentity as AgentIdentity
from .versioning import VersionBindings as VersionBindings


class StageAction(StrEnum):
    CLEAN = "CLEAN"
    REPAIR = "REPAIR"
    WARNING = "WARNING"
    HOLD = "HOLD"


class WarningStage(StrEnum):
    LOGIC = "LOGIC"
    LAYOUT = "LAYOUT"


class SemanticDecision(StrEnum):
    PRESERVED = "PRESERVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class WarningRecord:
    code: str
    message: str
    evidence_hash: str

    def __post_init__(self) -> None:
        require_text(self.code, "code")
        require_text(self.message, "message")
        require_hash(self.evidence_hash, "evidence_hash")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "evidence_hash": self.evidence_hash,
        }


@dataclass(frozen=True, slots=True)
class WarningPolicyDecision:
    stage: WarningStage
    authorized: bool
    warning_evidence_hashes: tuple[str, ...]
    policy_version: str
    evidence_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage, WarningStage):
            raise TypeError("stage must be a WarningStage")
        if type(self.authorized) is not bool:
            raise TypeError("authorized must be bool")
        object.__setattr__(
            self, "warning_evidence_hashes", tuple(self.warning_evidence_hashes)
        )
        for item in self.warning_evidence_hashes:
            require_hash(item, "warning_evidence_hashes")
        require_text(self.policy_version, "policy_version")
        require_hash(self.evidence_hash, "evidence_hash")


@dataclass(frozen=True, slots=True)
class StageAssessment:
    action: StageAction
    evidence_hash: str
    warnings: tuple[WarningRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.action, StageAction):
            raise TypeError("action must be StageAction")
        require_hash(self.evidence_hash, "evidence_hash")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if (self.action is StageAction.WARNING) != bool(self.warnings):
            raise ValueError("only WARNING requires warnings")


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    job_id: str
    run_id: str
    request_hash: str
    question_hash: str
    plan_hash: str
    source_code: str
    code_ref: str
    render_manifest_ref: str
    render_config_hash: str
    assets_hash: str
    external_dependencies_hash: str
    ordered_scene_ids: tuple[str, ...]
    environment_evidence_hash: str
    versions: VersionBindings

    def __post_init__(self) -> None:
        for name in (
            "job_id",
            "run_id",
            "source_code",
            "code_ref",
            "render_manifest_ref",
        ):
            require_text(getattr(self, name), name)
        for name in (
            "request_hash",
            "question_hash",
            "plan_hash",
            "render_config_hash",
            "assets_hash",
            "external_dependencies_hash",
            "environment_evidence_hash",
        ):
            require_hash(getattr(self, name), name)
        object.__setattr__(self, "ordered_scene_ids", tuple(self.ordered_scene_ids))
        if not self.ordered_scene_ids or len(set(self.ordered_scene_ids)) != len(
            self.ordered_scene_ids
        ):
            raise ValueError("ordered_scene_ids must be non-empty and unique")
        for scene_id in self.ordered_scene_ids:
            require_text(scene_id, "ordered_scene_ids")


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    result: QualityResult
    snapshot: QualityJobSnapshot
