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
