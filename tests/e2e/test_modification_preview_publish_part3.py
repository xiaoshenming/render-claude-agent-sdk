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



from .test_modification_preview_publish_support1 import *
from .test_modification_preview_publish_support2 import *
def test_explicit_approval_creates_user_revision_and_quality_reentry_payload() -> None:
    repository = MemoryModificationRepository()
    renderer = FakePreviewRenderer()
    service = ModificationService(
        repository,
        StaticContext(_context()),
        FakeExecutor(SOURCE.replace('Text("old")', 'Text("fixed")')),
        renderer,
    )
    draft = service.create_preview(
        tenant_id="tenant-a",
        job_id="job-1",
        instruction="Correct the proof label.",
        target_scene_ids=("Proof",),
        idempotency_key="request-3",
    )

    receipt = service.approve("tenant-a", "job-1", draft.draft_id, expected_version=0)

    revision, baseline, quality_job_id, payload = repository.approvals[0]
    assert receipt.draft.state is DraftState.APPROVED
    assert revision.stage is RevisionStage.USER_MODIFICATION
    assert payload["source_revision_id"] == revision.revision_id
    assert payload["source_code"] == draft.candidate_source
    assert payload["stage_run_id"] == receipt.stage_run_id
    assert baseline.stage is RevisionStage.BASELINE
    assert baseline.revision_id == renderer.requests[0].revision_id
    assert payload["job_id"] == quality_job_id == receipt.quality_job_id


def test_approved_user_revision_reenters_complete_orchestrator_flow(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "reentry.sqlite3")
    repository.create_job("job-1", happy_baseline())
    initial = quality_service(repository, StageAction.CLEAN, StageAction.CLEAN).execute(
        happy_request()
    )
    candidate = happy_request().source_code.replace(
        "item.shift(RIGHT)", "item.shift(LEFT)"
    )
    child_job_id = "job-1:mod:reentry"
    child_baseline = Revision(
        "baseline-job-1-mod-reentry",
        None,
        RevisionStage.BASELINE,
        code_hash(candidate),
        semantic_fingerprint(candidate),
        scene_fingerprints(candidate),
        sha256_text("preview-reentry"),
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.USER,
        0,
    )
    repository.create_job(child_job_id, child_baseline)
    request = replace(
        happy_request(),
        job_id=child_job_id,
        run_id="run-user-modification",
        request_hash=sha256_text("request:user-modification"),
        source_code=candidate,
        code_ref="revision://user-mod-reentry",
        render_manifest_ref="evidence://preview-reentry",
    )

    result = quality_service(repository, StageAction.CLEAN, StageAction.CLEAN).execute(
        request
    )
    repository.close()

    assert initial.snapshot.state is QualityState.ACCEPTED
    assert result.result.accepted_revision_id == child_baseline.revision_id
    assert result.snapshot.state is QualityState.ACCEPTED


def test_modification_api_requires_tenant_scope_and_explicit_approval(
    tmp_path: Path,
) -> None:
    repository = MemoryModificationRepository()
    service = ModificationService(
        repository,
        StaticContext(_context()),
        FakeExecutor(SOURCE.replace('Text("old")', 'Text("fixed")')),
        FakePreviewRenderer(),
    )
    auth = GatewayHmacAuthenticator(b"modification-api-secret", max_age_seconds=300)
    app = create_app(
        ApiSettings(database=tmp_path / "api.sqlite3"),
        authenticator=auth,
        modification_service_factory=lambda: service,
    )
    with TestClient(app) as client:
        created = client.post(
            "/v1/quality/jobs/job-1/modifications",
            headers=auth.headers("tenant-a"),
            json={
                "instruction": "Correct the proof label.",
                "target_scene_ids": ["Proof"],
                "idempotency_key": "api-request-1",
            },
        )
        draft_id = created.json()["draft_id"]
        hidden = client.get(
            f"/v1/quality/jobs/job-1/modifications/{draft_id}",
            headers=auth.headers("tenant-b"),
        )
        approved = client.post(
            f"/v1/quality/jobs/job-1/modifications/{draft_id}/approve",
            headers=auth.headers("tenant-a"),
            json={"expected_version": 0},
        )

    assert created.status_code == 201
    assert hidden.status_code == 404
    assert approved.status_code == 200
    assert approved.json()["draft"]["state"] == "APPROVED"
