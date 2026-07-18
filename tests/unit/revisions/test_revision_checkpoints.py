import sqlite3
from pathlib import Path

import pytest
from test_repository_rules import make_revision

from manim_quality.contracts import RevisionStage
from manim_quality.revisions.store import (
    Checkpoint,
    CheckpointConflict,
    RepositoryTransactionError,
    RevisionJobMismatch,
    RevisionNotFound,
    StaleWrite,
)
from manim_quality.storage.database import SQLiteRevisionRepository


def prepared_repository(path: str = ":memory:") -> SQLiteRevisionRepository:
    repository = SQLiteRevisionRepository(path)
    repository.create_job("job-1", make_revision("base-1"))
    child = make_revision("child-1", parent="base-1", stage=RevisionStage.LOGIC_REPAIR)
    repository.append_revision("job-1", child, expected_version=0)
    return repository


def evidence_hash(marker: str) -> str:
    return make_revision(f"evidence-{marker}").code_hash


def prepare_checkpoint(
    repository: SQLiteRevisionRepository, checkpoint: Checkpoint
) -> None:
    if checkpoint in {Checkpoint.LAYOUT_CERTIFIED, Checkpoint.DELIVERY}:
        snapshot = repository.get_job("job-1")
        repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "child-1",
            evidence_hash=evidence_hash("logic"),
            expected_version=snapshot.version,
        )
    if checkpoint is Checkpoint.DELIVERY:
        snapshot = repository.get_job("job-1")
        repository.promote_checkpoint(
            "job-1",
            Checkpoint.LAYOUT_CERTIFIED,
            "child-1",
            evidence_hash=evidence_hash("layout"),
            expected_version=snapshot.version,
        )


@pytest.mark.parametrize(
    ("checkpoint", "field"),
    [
        (Checkpoint.RENDER_BASELINE, "render_baseline_revision_id"),
        (Checkpoint.LOGIC_CERTIFIED, "logic_certified_revision_id"),
        (Checkpoint.LAYOUT_CERTIFIED, "layout_certified_revision_id"),
        (Checkpoint.DELIVERY, "delivery_revision_id"),
    ],
)
def test_checkpoint_cas_sets_only_requested_field(
    checkpoint: Checkpoint,
    field: str,
) -> None:
    repository = prepared_repository()
    try:
        prepare_checkpoint(repository, checkpoint)
        before = repository.get_job("job-1")

        if checkpoint is Checkpoint.RENDER_BASELINE:
            with pytest.raises(CheckpointConflict, match="immutable"):
                repository.promote_checkpoint(
                    "job-1",
                    checkpoint,
                    "child-1",
                    evidence_hash=evidence_hash("render"),
                    expected_version=before.version,
                )
            return
        after = repository.promote_checkpoint(
            "job-1",
            checkpoint,
            "child-1",
            evidence_hash=evidence_hash(checkpoint.name),
            expected_version=before.version,
        )

        assert after.version == before.version + 1
        assert getattr(after, field) == "child-1"
        assert after.state == before.state
    finally:
        repository.close()


def test_checkpoint_rejects_missing_cross_job_and_stale_revision() -> None:
    repository = prepared_repository()
    try:
        repository.create_job("job-2", make_revision("base-2"))

        with pytest.raises(RevisionNotFound):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.DELIVERY,
                "absent",
                evidence_hash=evidence_hash("missing"),
                expected_version=1,
            )
        with pytest.raises(RevisionJobMismatch):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.DELIVERY,
                "base-2",
                evidence_hash=evidence_hash("cross-job"),
                expected_version=1,
            )
        with pytest.raises(StaleWrite):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.LOGIC_CERTIFIED,
                "child-1",
                evidence_hash=evidence_hash("stale"),
                expected_version=0,
            )
        assert repository.get_job("job-1").version == 1
    finally:
        repository.close()


def test_checkpoint_rejects_untyped_name() -> None:
    repository = prepared_repository()
    try:
        with pytest.raises(TypeError, match="Checkpoint"):
            repository.promote_checkpoint(
                "job-1",
                "delivery",
                "child-1",
                evidence_hash=evidence_hash("untyped"),
                expected_version=1,  # type: ignore[arg-type]
            )
    finally:
        repository.close()


def test_database_failure_rolls_back_revision_and_version(tmp_path: Path) -> None:
    database = tmp_path / "rollback.sqlite3"
    repository = SQLiteRevisionRepository(database)
    repository.create_job("job-1", make_revision("base-1"))
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TRIGGER reject_version_update
            BEFORE UPDATE OF version ON quality_jobs
            BEGIN
                SELECT RAISE(ABORT, 'forced update failure');
            END;
            """
        )
    child = make_revision(
        "rolled-back", parent="base-1", stage=RevisionStage.LOGIC_REPAIR
    )

    with pytest.raises(RepositoryTransactionError, match="forced update failure"):
        repository.append_revision("job-1", child, expected_version=0)

    with pytest.raises(RevisionNotFound):
        repository.get_revision("rolled-back")
    assert repository.get_job("job-1").version == 0
    repository.close()
