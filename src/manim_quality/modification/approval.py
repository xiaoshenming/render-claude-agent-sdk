"""Deterministic revisions and queue payload for an approved draft."""

from __future__ import annotations

import json
from dataclasses import dataclass

from manim_quality.contracts import (
    PatchScope,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.revisions.fingerprint import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_bytes,
)

from .models import ModificationDraft


@dataclass(frozen=True, slots=True)
class ApprovalCommand:
    revision: Revision
    quality_baseline: Revision
    quality_job_id: str
    stage_run_id: str
    payload: bytes
    request_hash: str


def build_approval(request, draft: ModificationDraft) -> ApprovalCommand:
    quality_job_id = f"{draft.job_id}:mod:{draft.draft_id[6:22]}"
    stage_run_id = f"quality:{quality_job_id}:{draft.draft_id[6:18]}"
    payload = _quality_payload(request, draft, quality_job_id, stage_run_id)
    return ApprovalCommand(
        _user_revision(draft),
        _quality_baseline(draft, quality_job_id),
        quality_job_id,
        stage_run_id,
        payload,
        sha256_bytes(payload),
    )


def _user_revision(draft: ModificationDraft) -> Revision:
    return Revision(
        draft.candidate_revision_id,
        draft.parent_revision_id,
        RevisionStage.USER_MODIFICATION,
        code_hash(draft.candidate_source),
        semantic_fingerprint(draft.candidate_source),
        scene_fingerprints(draft.candidate_source),
        None,
        draft.target_scene_ids,
        PatchScope.USER_SCENES,
        RevisionCreator.USER,
        1,
    )


def _quality_baseline(draft: ModificationDraft, job_id: str) -> Revision:
    return Revision(
        f"baseline-{job_id}",
        None,
        RevisionStage.BASELINE,
        code_hash(draft.candidate_source),
        semantic_fingerprint(draft.candidate_source),
        scene_fingerprints(draft.candidate_source),
        draft.preview_manifest_hash,
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.USER,
        0,
    )


def _quality_payload(request, draft, job_id: str, run_id: str) -> bytes:
    payload = {
        "schema_version": 1,
        "job_id": job_id,
        "stage_run_id": run_id,
        "source_revision_id": draft.candidate_revision_id,
        "source_code": draft.candidate_source,
        "code_ref": f"revision://{draft.candidate_revision_id}",
        "render_manifest_ref": f"evidence://{draft.preview_manifest_hash}",
        "question_hash": request.question_hash,
        "plan_hash": request.plan_hash,
        "render_config_hash": request.render_config_hash,
        "assets_hash": request.assets_hash,
        "external_dependencies_hash": request.external_dependencies_hash,
        "ordered_scene_ids": list(request.ordered_scene_ids),
        "environment_evidence_hash": request.environment_evidence_hash,
        "versions": request.versions.to_dict(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
