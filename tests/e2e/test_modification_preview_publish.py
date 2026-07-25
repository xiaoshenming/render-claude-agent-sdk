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
from tests.e2e.test_quality_happy_path import VERSIONS
from tests.e2e.test_quality_happy_path import (
    baseline as happy_baseline,
)
from tests.e2e.test_quality_happy_path import (
    execution_request as happy_request,
)
from tests.e2e.test_quality_happy_path import (
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


def test_scene_plan_uses_stable_names_and_read_only_neighbors() -> None:
    plan = plan_modification(SOURCE, ("Proof",))

    assert plan.ordered_scene_ids == ("Intro", "Proof", "Summary")
    assert [region.scene_id for region in plan.editable_regions] == ["Proof"]
    assert [region.scene_id for region in plan.context_regions] == [
        "Intro",
        "Summary",
    ]
    assert plan.editable_regions[0].line_start < plan.editable_regions[0].line_end


def test_all_requested_scenes_must_change() -> None:
    plan = plan_modification(SOURCE, ("Intro", "Proof"))
    candidate = SOURCE.replace('Text("old")', 'Text("fixed")')

    with pytest.raises(ModificationScopeError, match="requested Scene unchanged"):
        validate_modification(SOURCE, candidate, plan)


@pytest.mark.parametrize(
    "candidate, reason",
    [
        (SOURCE.replace("SCALE = 1", "SCALE = 2"), "shared dependencies changed"),
        (
            SOURCE.replace('Text("Summary")', 'Text("changed")').replace(
                'Text("old")', 'Text("fixed")'
            ),
            "unrequested Scene changed",
        ),
    ],
)
def test_shared_or_unrequested_changes_fail_closed(candidate: str, reason: str) -> None:
    plan = plan_modification(SOURCE, ("Proof",))

    with pytest.raises(ModificationScopeError, match=reason):
        validate_modification(SOURCE, candidate, plan)


def test_scene_reordering_fails_closed() -> None:
    plan = plan_modification(SOURCE, ("Proof",))
    intro = SOURCE[SOURCE.index("class Intro") : SOURCE.index("class Proof")]
    candidate = SOURCE.replace(intro, "") + "\n" + intro

    with pytest.raises(ModificationScopeError, match="order or membership"):
        validate_modification(SOURCE, candidate, plan)


def test_inherited_scene_without_construct_can_be_targeted() -> None:
    source = """\
class BaseLesson(Scene):
    def construct(self):
        self.add(Dot())

class ConcreteLesson(BaseLesson):
    pass
"""

    plan = plan_modification(source, ("ConcreteLesson",))

    assert plan.ordered_scene_ids == ("BaseLesson", "ConcreteLesson")
    assert plan.editable_regions[0].scene_id == "ConcreteLesson"


def test_approval_atomically_appends_revision_and_full_quality_work(
    tmp_path: Path,
) -> None:
    database = _accepted_job(tmp_path)
    repository = SQLiteModificationRepository(database)
    draft = repository.create(_draft())

    receipt = repository.approve(
        draft,
        _user_revision(draft),
        _quality_baseline(draft, "job-1:mod:draft-1"),
        "job-1:mod:draft-1",
        b'{"source_revision_id":"user-mod-1"}',
        sha256_bytes(b'{"source_revision_id":"user-mod-1"}'),
        "quality:job-1:mod:draft-1",
        expected_version=0,
        now=datetime(2026, 7, 12, tzinfo=UTC),
    )

    assert receipt.draft.state is DraftState.APPROVED
    connection = open_sqlite(database)
    original = connection.execute(
        "SELECT state FROM quality_jobs WHERE job_id='job-1'"
    ).fetchone()
    child = connection.execute(
        "SELECT state FROM quality_jobs WHERE job_id='job-1:mod:draft-1'"
    ).fetchone()
    queued = connection.execute(
        "SELECT state FROM quality_queue WHERE stage_run_id=?",
        (receipt.stage_run_id,),
    ).fetchone()
    revision = connection.execute(
        "SELECT stage FROM quality_revisions WHERE revision_id='user-mod-1'"
    ).fetchone()
    connection.close()
    repository.close()

    assert original["state"] == QualityState.ACCEPTED.value
    assert child["state"] == QualityState.BASELINE_READY.value
    assert queued["state"] == "QUEUED"
    assert revision["stage"] == RevisionStage.USER_MODIFICATION.value


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


def _context() -> ModificationContext:
    impact = analyze_source(SOURCE, ("Intro", "Proof", "Summary"))
    preview = RenderRequest(
        "baseline-1",
        SOURCE,
        code_hash(SOURCE),
        impact.scene_hashes,
        ("Intro", "Proof", "Summary"),
        {},
        sha256_text("render-config"),
        "renderer-v1",
        sha256_text("assets"),
    )
    quality = ExecutionRequest(
        "job-1",
        "old-run",
        sha256_text("old-request"),
        sha256_text("question"),
        sha256_text("plan"),
        SOURCE,
        "artifact://candidate.py",
        "artifact://render.json",
        sha256_text("render-config"),
        sha256_text("assets"),
        sha256_text("external"),
        ("Intro", "Proof", "Summary"),
        sha256_text("environment"),
        VERSIONS,
    )
    return ModificationContext(
        "tenant-a", "job-1", "baseline-1", SOURCE, preview, quality
    )


def _artifact(label: str) -> ArtifactRef:
    content = label.encode()
    return ArtifactRef(
        f"artifact://{label}", sha256_bytes(content), len(content), "video/mp4"
    )
