from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import GatewayHmacAuthenticator
from apps.api.main import ApiSettings, create_app
from manim_quality.contracts import (
    PatchScope,
    QualityState,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.modification.errors import ModificationNotFound
from manim_quality.modification.models import (
    ApprovalReceipt,
    DraftState,
    ModificationContext,
    ModificationDraft,
)
from manim_quality.modification.planner import (
    ModificationScopeError,
    plan_modification,
    validate_modification,
)
from manim_quality.modification.repository import (
    SQLiteModificationRepository,
)
from manim_quality.modification.service import ModificationService
from manim_quality.orchestrator.models import ExecutionRequest, StageAction
from manim_quality.rendering.impact import analyze_source
from manim_quality.rendering.interfaces import RenderEvidence, RenderRequest
from manim_quality.rendering.manifest import ManifestSlice, RenderManifest
from manim_quality.rendering.slices import RenderPlan
from manim_quality.revisions.fingerprint import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_bytes,
    sha256_text,
)
from manim_quality.storage import ArtifactRef
from manim_quality.storage._sqlite import open_sqlite
from manim_quality.storage.database import SQLiteRevisionRepository
from manim_quality.storage.intake import IntakeLimits, SQLiteIntakeRepository
from .test_quality_happy_path import VERSIONS
from .test_quality_happy_path import (
    baseline as happy_baseline,
)
from .test_quality_happy_path import (
    execution_request as happy_request,
)
from .test_quality_happy_path import (
    service as quality_service,
)

SOURCE = """\
from manim import *

SCALE = 1

class Intro(Scene):
    def construct(self):
        self.play(Write(Text("Intro")))

class Proof(Scene):
    def construct(self):
        self.play(Write(Text("old")))

class Summary(Scene):
    def construct(self):
        self.play(Write(Text("Summary")))
"""



def _accepted_job(tmp_path: Path) -> Path:
    database = tmp_path / "quality.sqlite3"
    baseline = Revision(
        "baseline-1",
        None,
        RevisionStage.BASELINE,
        code_hash(SOURCE),
        semantic_fingerprint(SOURCE),
        scene_fingerprints(SOURCE),
        sha256_text("baseline-render"),
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.SYSTEM,
        0,
    )
    revisions = SQLiteRevisionRepository(database)
    revisions.create_job("job-1", baseline)
    revisions.close()
    intake = SQLiteIntakeRepository(database)
    intake.submit(_submission(), IntakeLimits())
    intake.close()
    connection = open_sqlite(database)
    connection.execute(
        "UPDATE quality_jobs SET state=? WHERE job_id='job-1'",
        (QualityState.ACCEPTED.value,),
    )
    connection.close()
    return database


def _submission() -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": "job-1",
        "tenant_id": "tenant-a",
        "candidate_code_ref": "artifact://candidate.py",
        "problem_text": "Modify the proof scene.",
        "planning": {"scenes": ["Intro", "Proof", "Summary"]},
        "expected_answer": None,
        "render_manifest_ref": "artifact://render.json",
        "asset_manifest_ref": None,
        "callback_url": None,
        "idempotency_key": "initial-job",
    }


def _draft() -> ModificationDraft:
    candidate = SOURCE.replace('Text("old")', 'Text("fixed")')
    return ModificationDraft(
        "draft-1",
        "tenant-a",
        "job-1",
        "mod-idem-1",
        sha256_text("mod-request"),
        "baseline-1",
        "user-mod-1",
        "Correct the proof label.",
        ("Proof",),
        candidate,
        sha256_text("preview-manifest"),
        sha256_text("preview-video"),
        DraftState.PREVIEW_READY,
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


class StaticContext:
    def __init__(self, context: ModificationContext) -> None:
        self.context = context

    def load(self, tenant_id: str, job_id: str) -> ModificationContext:
        del tenant_id, job_id
        return self.context


class FakeExecutor:
    def __init__(self, candidate: str) -> None:
        self.candidate = candidate
        self.calls: list[object] = []

    def patch_source(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "CoderResult",
            (),
            {"source_code": self.candidate, "changed_scene_ids": ("Proof",)},
        )()


class FakePreviewRenderer:
    def __init__(self, *, fail: bool = False) -> None:
        self.requests: list[RenderRequest] = []
        self.fail = fail

    def render(self, request: RenderRequest) -> RenderEvidence:
        self.requests.append(request)
        if self.fail:
            return RenderEvidence(
                False,
                RenderPlan(request.ordered_scene_ids, {}, False, ()),
                failure_message="injected preview failure",
            )
        slices = tuple(
            ManifestSlice(
                scene_id,
                request.scene_hashes[scene_id],
                _artifact(f"slice-{scene_id}"),
                False,
            )
            for scene_id in request.ordered_scene_ids
        )
        manifest = RenderManifest(
            request.revision_id,
            request.code_hash,
            request.render_config_hash,
            request.renderer_version,
            request.assets_hash,
            sha256_text("external"),
            sha256_text("environment"),
            "environment-v1",
            True,
            False,
            slices,
            _artifact("preview-video"),
        )
        return RenderEvidence(
            True,
            RenderPlan(request.ordered_scene_ids, {}, False, ()),
            manifest,
        )


class MemoryModificationRepository:
    def __init__(self) -> None:
        self.items: dict[str, ModificationDraft] = {}
        self.approvals: list[tuple[Revision, Revision, str, dict[str, object]]] = []

    def create(self, draft: ModificationDraft) -> ModificationDraft:
        self.items[draft.draft_id] = draft
        return draft

    def get(self, tenant_id: str, job_id: str, draft_id: str) -> ModificationDraft:
        draft = self.items.get(draft_id)
        if draft is None or (draft.tenant_id, draft.job_id) != (tenant_id, job_id):
            raise KeyError(draft_id)
        return draft

    def approve(
        self,
        draft,
        revision,
        quality_baseline,
        quality_job_id,
        queue_payload,
        queue_request_hash,
        stage_run_id,
        *,
        expected_version,
        now,
    ):
        del queue_request_hash, expected_version, now
        import json

        self.approvals.append(
            (revision, quality_baseline, quality_job_id, json.loads(queue_payload))
        )
        approved = replace(
            draft,
            state=DraftState.APPROVED,
            version=draft.version + 1,
            quality_run_id=stage_run_id,
            quality_job_id=quality_job_id,
        )
        self.items[draft.draft_id] = approved
        return ApprovalReceipt(approved, stage_run_id, quality_job_id)

    def discard(self, tenant_id, job_id, draft_id, *, expected_version):
        del expected_version
        draft = self.get(tenant_id, job_id, draft_id)
        discarded = replace(draft, state=DraftState.DISCARDED, version=1)
        self.items[draft_id] = discarded
        return discarded

    def close(self) -> None:
        pass
