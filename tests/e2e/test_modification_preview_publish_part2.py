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
def test_approval_failure_rolls_back_draft_revision_queue_and_job(
    tmp_path: Path,
) -> None:
    database = _accepted_job(tmp_path)

    def fail() -> None:
        raise RuntimeError("injected approval failure")

    repository = SQLiteModificationRepository(database, approval_probe=fail)
    draft = repository.create(_draft())
    with pytest.raises(RuntimeError, match="injected"):
        repository.approve(
            draft,
            _user_revision(draft),
            _quality_baseline(draft, "job-1:mod:draft-1"),
            "job-1:mod:draft-1",
            b"{}",
            sha256_bytes(b"{}"),
            "quality:job-1:mod:draft-1",
            expected_version=0,
            now=datetime(2026, 7, 12, tzinfo=UTC),
        )

    stored = repository.get("tenant-a", "job-1", "draft-1")
    assert stored.state is DraftState.PREVIEW_READY
    connection = open_sqlite(database)
    assert (
        connection.execute(
            "SELECT 1 FROM quality_revisions WHERE revision_id='user-mod-1'"
        ).fetchone()
        is None
    )
    assert (
        connection.execute(
            "SELECT state FROM quality_jobs WHERE job_id='job-1'"
        ).fetchone()["state"]
        == QualityState.ACCEPTED.value
    )
    assert (
        connection.execute(
            "SELECT 1 FROM quality_queue WHERE stage_run_id='quality:job-1:mod:draft-1'"
        ).fetchone()
        is None
    )
    assert (
        connection.execute(
            "SELECT 1 FROM quality_jobs WHERE job_id='job-1:mod:draft-1'"
        ).fetchone()
        is None
    )
    connection.close()
    repository.close()


def test_draft_reads_are_tenant_scoped_and_discard_is_idempotent(
    tmp_path: Path,
) -> None:
    repository = SQLiteModificationRepository(_accepted_job(tmp_path))
    repository.create(_draft())

    with pytest.raises(ModificationNotFound):
        repository.get("tenant-b", "job-1", "draft-1")
    discarded = repository.discard("tenant-a", "job-1", "draft-1", expected_version=0)
    replay = repository.discard("tenant-a", "job-1", "draft-1", expected_version=0)
    repository.close()

    assert discarded.state is DraftState.DISCARDED
    assert discarded.version == 1
    assert replay == discarded


def test_preview_is_targeted_and_does_not_run_full_quality_chain() -> None:
    context = _context()
    repository = MemoryModificationRepository()
    executor = FakeExecutor(SOURCE.replace('Text("old")', 'Text("fixed")'))
    renderer = FakePreviewRenderer()
    service = ModificationService(
        repository, StaticContext(context), executor, renderer
    )

    draft = service.create_preview(
        tenant_id="tenant-a",
        job_id="job-1",
        instruction="Correct the proof label.",
        target_scene_ids=("Proof",),
        idempotency_key="request-1",
    )

    assert draft.state is DraftState.PREVIEW_READY
    assert draft.target_scene_ids == ("Proof",)
    assert renderer.requests[0].revision_id == (
        f"baseline-job-1:mod:{draft.draft_id[6:22]}"
    )
    assert renderer.requests[0].source_code == draft.candidate_source
    assert len(executor.calls) == 1


def test_service_independently_rejects_silent_partial_application() -> None:
    repository = MemoryModificationRepository()
    executor = FakeExecutor(SOURCE.replace('Text("old")', 'Text("fixed")'))
    renderer = FakePreviewRenderer()
    service = ModificationService(
        repository, StaticContext(_context()), executor, renderer
    )

    with pytest.raises(ModificationScopeError, match="requested Scene unchanged"):
        service.create_preview(
            tenant_id="tenant-a",
            job_id="job-1",
            instruction="Update both scenes.",
            target_scene_ids=("Intro", "Proof"),
            idempotency_key="request-2",
        )

    assert renderer.requests == []
    assert repository.items == {}


def test_idempotency_conflict_is_rejected_before_another_agent_call() -> None:
    repository = MemoryModificationRepository()
    executor = FakeExecutor(SOURCE.replace('Text("old")', 'Text("fixed")'))
    service = ModificationService(
        repository, StaticContext(_context()), executor, FakePreviewRenderer()
    )
    service.create_preview(
        tenant_id="tenant-a",
        job_id="job-1",
        instruction="Correct the proof label.",
        target_scene_ids=("Proof",),
        idempotency_key="same-key",
    )

    with pytest.raises(RuntimeError, match="different payload"):
        service.create_preview(
            tenant_id="tenant-a",
            job_id="job-1",
            instruction="Use a different label.",
            target_scene_ids=("Proof",),
            idempotency_key="same-key",
        )

    assert len(executor.calls) == 1


def test_preview_failure_is_persisted_but_cannot_be_approved() -> None:
    repository = MemoryModificationRepository()
    service = ModificationService(
        repository,
        StaticContext(_context()),
        FakeExecutor(SOURCE.replace('Text("old")', 'Text("fixed")')),
        FakePreviewRenderer(fail=True),
    )

    draft = service.create_preview(
        tenant_id="tenant-a",
        job_id="job-1",
        instruction="Correct the proof label.",
        target_scene_ids=("Proof",),
        idempotency_key="failed-preview",
    )

    assert draft.state is DraftState.FAILED
    assert draft.failure_reason == "targeted preview failed: injected preview failure"
    with pytest.raises(RuntimeError, match="cannot approve FAILED"):
        service.approve("tenant-a", "job-1", draft.draft_id, expected_version=0)
