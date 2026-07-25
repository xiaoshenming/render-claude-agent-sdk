"""Immutable contracts for user modification drafts and approvals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from manim_quality.orchestrator.models import ExecutionRequest
from manim_quality.rendering.interfaces import RenderRequest


class DraftState(StrEnum):
    PREVIEW_READY = "PREVIEW_READY"
    FAILED = "FAILED"
    APPROVED = "APPROVED"
    DISCARDED = "DISCARDED"


@dataclass(frozen=True, slots=True)
class ModificationContext:
    tenant_id: str
    job_id: str
    parent_revision_id: str
    source_code: str
    preview_request: RenderRequest
    quality_request: ExecutionRequest


@dataclass(frozen=True, slots=True)
class ModificationDraft:
    draft_id: str
    tenant_id: str
    job_id: str
    idempotency_key: str
    request_hash: str
    parent_revision_id: str
    candidate_revision_id: str
    instruction: str
    target_scene_ids: tuple[str, ...]
    candidate_source: str
    preview_manifest_hash: str | None
    preview_video_hash: str | None
    state: DraftState
    version: int = 0
    failure_reason: str | None = None
    quality_run_id: str | None = None
    quality_job_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "draft_id",
            "tenant_id",
            "job_id",
            "idempotency_key",
            "request_hash",
            "parent_revision_id",
            "candidate_revision_id",
            "instruction",
            "candidate_source",
        ):
            _text(getattr(self, name), name)
        object.__setattr__(self, "target_scene_ids", tuple(self.target_scene_ids))
        if not self.target_scene_ids or len(set(self.target_scene_ids)) != len(
            self.target_scene_ids
        ):
            raise ValueError("target_scene_ids must be non-empty and unique")
        if not isinstance(self.state, DraftState):
            raise TypeError("state must be DraftState")
        if self.version < 0:
            raise ValueError("version must be non-negative")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "draft_id": self.draft_id,
            "job_id": self.job_id,
            "parent_revision_id": self.parent_revision_id,
            "candidate_revision_id": self.candidate_revision_id,
            "instruction": self.instruction,
            "target_scene_ids": list(self.target_scene_ids),
            "preview_manifest_hash": self.preview_manifest_hash,
            "preview_video_hash": self.preview_video_hash,
            "state": self.state.value,
            "version": self.version,
            "failure_reason": self.failure_reason,
            "quality_run_id": self.quality_run_id,
            "quality_job_id": self.quality_job_id,
        }


@dataclass(frozen=True, slots=True)
class ApprovalReceipt:
    draft: ModificationDraft
    stage_run_id: str
    quality_job_id: str


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
