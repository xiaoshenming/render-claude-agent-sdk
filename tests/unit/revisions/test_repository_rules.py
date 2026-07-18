from dataclasses import FrozenInstanceError, replace

import pytest

from manim_quality.contracts import (
    PatchScope,
    QualityState,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.revisions.fingerprint import sha256_text
from manim_quality.revisions.store import (
    CheckpointOrderError,
    JobConflict,
    ParentRevisionError,
    RevisionConflict,
    RevisionNotFound,
    RevisionRepository,
    StaleWrite,
)
from manim_quality.storage.database import SQLiteRevisionRepository


def make_revision(
    revision_id: str,
    *,
    parent: str | None = None,
    stage: RevisionStage = RevisionStage.BASELINE,
    marker: str = "baseline",
) -> Revision:
    return Revision(
        revision_id=revision_id,
        parent_revision_id=parent,
        stage=stage,
        code_hash=sha256_text(f"code:{marker}"),
        semantic_fingerprint=sha256_text(f"semantic:{marker}"),
        scene_hashes={"Lesson": sha256_text(f"scene:{marker}")},
        render_manifest_hash=sha256_text(f"render:{marker}"),
        changed_scene_ids=[] if parent is None else ["Lesson"],
        patch_scope=(
            PatchScope.FULL_CANDIDATE if parent is None else PatchScope.SCENE_LOGIC
        ),
        created_by=(
            RevisionCreator.SYSTEM if parent is None else RevisionCreator.LOGIC_AGENT
        ),
        attempt=0 if parent is None else 1,
    )


@pytest.fixture
def repository() -> SQLiteRevisionRepository:
    repo = SQLiteRevisionRepository(":memory:")
    yield repo
    repo.close()


def test_create_job_binds_immutable_baseline_snapshot(
    repository: SQLiteRevisionRepository,
) -> None:
    baseline = make_revision("rev-base")

    snapshot = repository.create_job("job-1", baseline)

    assert isinstance(repository, RevisionRepository)
    assert snapshot.job_id == "job-1"
    assert snapshot.version == 0
    assert snapshot.state is QualityState.BASELINE_READY
    assert snapshot.render_baseline_revision_id == "rev-base"
    assert snapshot.logic_certified_revision_id is None
    assert snapshot.layout_certified_revision_id is None
    assert snapshot.delivery_revision_id is None
    assert repository.get_job("job-1") == snapshot
    assert repository.get_revision("rev-base") == baseline
    with pytest.raises(FrozenInstanceError):
        snapshot.version = 1  # type: ignore[misc]


def test_create_job_is_idempotent_only_for_same_baseline(
    repository: SQLiteRevisionRepository,
) -> None:
    baseline = make_revision("rev-base")
    first = repository.create_job("job-1", baseline)

    assert repository.create_job("job-1", baseline) == first

    with pytest.raises(JobConflict, match="different baseline"):
        repository.create_job("job-1", make_revision("rev-other"))


def test_append_is_idempotent_but_revision_payload_cannot_be_overwritten(
    repository: SQLiteRevisionRepository,
) -> None:
    repository.create_job("job-1", make_revision("rev-base"))
    child = make_revision(
        "rev-child", parent="rev-base", stage=RevisionStage.LOGIC_REPAIR
    )

    appended = repository.append_revision("job-1", child, expected_version=0)

    assert appended.version == 1
    assert repository.append_revision("job-1", child, expected_version=0) == appended
    conflicting = make_revision(
        "rev-child",
        parent="rev-base",
        stage=RevisionStage.LOGIC_REPAIR,
        marker="different",
    )
    with pytest.raises(RevisionConflict, match="different payload"):
        repository.append_revision("job-1", conflicting, expected_version=1)
    assert repository.get_revision("rev-child") == child


def test_append_rejects_missing_cross_job_and_second_root_parents(
    repository: SQLiteRevisionRepository,
) -> None:
    repository.create_job("job-1", make_revision("base-1"))
    repository.create_job("job-2", make_revision("base-2"))

    invalid = [
        make_revision("missing", parent="absent", stage=RevisionStage.LOGIC_REPAIR),
        make_revision("cross", parent="base-2", stage=RevisionStage.LOGIC_REPAIR),
        make_revision("root-2", stage=RevisionStage.LOGIC_REPAIR),
        make_revision("base-child", parent="base-1", stage=RevisionStage.BASELINE),
    ]
    for revision in invalid:
        with pytest.raises(ParentRevisionError):
            repository.append_revision("job-1", revision, expected_version=0)

    assert repository.get_job("job-1").version == 0


def test_stale_append_rolls_back_insert(repository: SQLiteRevisionRepository) -> None:
    repository.create_job("job-1", make_revision("rev-base"))
    child = make_revision(
        "rev-stale", parent="rev-base", stage=RevisionStage.LOGIC_REPAIR
    )

    with pytest.raises(StaleWrite, match="expected version 9"):
        repository.append_revision("job-1", child, expected_version=9)

    with pytest.raises(RevisionNotFound):
        repository.get_revision("rev-stale")
    assert repository.get_job("job-1").version == 0


def test_repository_rejects_invalid_baseline_and_inputs(
    repository: SQLiteRevisionRepository,
) -> None:
    invalid_baseline = make_revision(
        "not-base", parent="parent", stage=RevisionStage.LOGIC_REPAIR
    )
    with pytest.raises(ParentRevisionError):
        repository.create_job("job-1", invalid_baseline)
    with pytest.raises(TypeError):
        repository.create_job("job-1", object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repository.get_job("")


def test_create_job_requires_successful_render_evidence(
    repository: SQLiteRevisionRepository,
) -> None:
    baseline = replace(make_revision("missing-render"), render_manifest_hash=None)

    with pytest.raises(CheckpointOrderError, match="render manifest hash"):
        repository.create_job("job-1", baseline)


def test_existing_revision_cannot_be_claimed_as_another_job(
    repository: SQLiteRevisionRepository,
) -> None:
    repository.create_job("job-1", make_revision("shared-id"))

    with pytest.raises(RevisionConflict, match="another job"):
        repository.create_job("job-2", make_revision("shared-id"))


def test_idempotent_job_rejects_changed_baseline_payload(
    repository: SQLiteRevisionRepository,
) -> None:
    repository.create_job("job-1", make_revision("base-1"))

    with pytest.raises(RevisionConflict, match="different payload"):
        repository.create_job("job-1", make_revision("base-1", marker="changed"))
