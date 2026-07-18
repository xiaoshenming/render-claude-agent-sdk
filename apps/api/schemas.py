"""Versioned API response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from manim_quality.contracts import DeliveryDecision, QualityState
from manim_quality.storage.queue_models import QueueState


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReceiptResponse(StrictResponse):
    schema_version: int = 1
    job_id: str
    stage_run_id: str
    queue_state: QueueState


class QualityResultResponse(StrictResponse):
    schema_version: int
    job_id: str
    decision: DeliveryDecision
    accepted_revision_id: str | None
    final_code_ref: str | None
    final_render_manifest_ref: str | None
    certificate_ref: str | None
    warnings: list[str]
    token_usage: dict[str, int]
    timings_ms: dict[str, int]


class JobResponse(StrictResponse):
    schema_version: int = 1
    job_id: str
    quality_state: QualityState | None
    queue_state: QueueState
    terminal_reason: str | None
    result: QualityResultResponse | None


class RevisionListResponse(StrictResponse):
    schema_version: int = 1
    job_id: str
    items: list[dict[str, object]]


class EvidenceResponse(StrictResponse):
    schema_version: int = 1
    job_id: str
    evidence_hashes: list[str]


class CertificateResponse(StrictResponse):
    schema_version: int = 1
    job_id: str
    evidence_hash: str
    payload: dict[str, object]


class ModificationDraftResponse(StrictResponse):
    schema_version: int = 1
    draft_id: str
    job_id: str
    parent_revision_id: str
    candidate_revision_id: str
    instruction: str
    target_scene_ids: list[str]
    preview_manifest_hash: str | None
    preview_video_hash: str | None
    state: str
    version: int
    failure_reason: str | None
    quality_run_id: str | None
    quality_job_id: str | None


class ModificationApprovalResponse(StrictResponse):
    schema_version: int = 1
    draft: ModificationDraftResponse
    stage_run_id: str
    quality_job_id: str
