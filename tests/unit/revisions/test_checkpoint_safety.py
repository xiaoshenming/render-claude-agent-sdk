import sqlite3

import pytest
from test_repository_rules import make_revision

from manim_quality.contracts import RevisionStage
from manim_quality.revisions.store import (
    Checkpoint,
    CheckpointConflict,
    CheckpointOrderError,
)
from manim_quality.storage.database import SQLiteRevisionRepository


def prepared_repository() -> SQLiteRevisionRepository:
    repository = SQLiteRevisionRepository(":memory:")
    repository.create_job("job-1", make_revision("base-1"))
    child = make_revision("child-1", parent="base-1", stage=RevisionStage.LOGIC_REPAIR)
    repository.append_revision("job-1", child, expected_version=0)
    return repository


def test_render_baseline_checkpoint_is_immutable() -> None:
    repository = prepared_repository()
    try:
        before = repository.get_job("job-1")
        with pytest.raises(CheckpointConflict, match="immutable"):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.RENDER_BASELINE,
                "child-1",
                evidence_hash=make_revision("render-evidence").code_hash,
                expected_version=before.version,
            )
        assert repository.get_job("job-1") == before
    finally:
        repository.close()


def test_checkpoint_rejects_noncanonical_evidence_before_mutation() -> None:
    repository = prepared_repository()
    try:
        before = repository.get_job("job-1")
        with pytest.raises(ValueError, match="canonical sha256"):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.LOGIC_CERTIFIED,
                "child-1",
                evidence_hash="not-a-hash",
                expected_version=before.version,
            )
        assert repository.get_job("job-1") == before
    finally:
        repository.close()


def test_checkpoint_promotion_is_ordered_and_evidence_bound() -> None:
    repository = prepared_repository()
    evidence = make_revision("logic-evidence", marker="logic-evidence").code_hash
    try:
        before = repository.get_job("job-1")
        with pytest.raises(CheckpointOrderError, match="LOGIC_CERTIFIED"):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.LAYOUT_CERTIFIED,
                "child-1",
                evidence_hash=evidence,
                expected_version=before.version,
            )

        promoted = repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "child-1",
            evidence_hash=evidence,
            expected_version=before.version,
        )
        assert promoted.logic_certified_evidence_hash == evidence
    finally:
        repository.close()


def test_same_checkpoint_retry_is_idempotent_but_evidence_cannot_change() -> None:
    repository = prepared_repository()
    evidence = make_revision("logic-evidence", marker="logic-evidence").code_hash
    try:
        before = repository.get_job("job-1")
        promoted = repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "child-1",
            evidence_hash=evidence,
            expected_version=before.version,
        )

        retried = repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "child-1",
            evidence_hash=evidence,
            expected_version=before.version,
        )
        assert retried == promoted

        with pytest.raises(CheckpointConflict, match="different evidence"):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.LOGIC_CERTIFIED,
                "child-1",
                evidence_hash=make_revision(
                    "other-evidence", marker="other-evidence"
                ).code_hash,
                expected_version=promoted.version,
            )
    finally:
        repository.close()


def test_revision_and_checkpoint_history_reject_direct_mutation() -> None:
    repository = prepared_repository()
    evidence = make_revision("logic-evidence", marker="logic-evidence").code_hash
    try:
        before = repository.get_job("job-1")
        repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "child-1",
            evidence_hash=evidence,
            expected_version=before.version,
        )
        connection = repository._connection  # type: ignore[attr-defined]

        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute(
                "UPDATE quality_revisions SET code_hash = code_hash "
                "WHERE revision_id = 'child-1'"
            )
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute(
                "DELETE FROM quality_checkpoint_history WHERE job_id = 'job-1'"
            )
    finally:
        repository.close()


def test_checkpoint_cannot_move_to_a_sibling_but_can_advance_to_a_child() -> None:
    repository = prepared_repository()
    try:
        sibling = make_revision(
            "sibling", parent="base-1", stage=RevisionStage.LOGIC_REPAIR
        )
        snapshot = repository.append_revision("job-1", sibling, expected_version=1)
        snapshot = repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "child-1",
            evidence_hash=make_revision("first", marker="first").code_hash,
            expected_version=snapshot.version,
        )

        with pytest.raises(CheckpointConflict, match="non-descendant"):
            repository.promote_checkpoint(
                "job-1",
                Checkpoint.LOGIC_CERTIFIED,
                "sibling",
                evidence_hash=make_revision("sibling-evidence").code_hash,
                expected_version=snapshot.version,
            )

        grandchild = make_revision(
            "grandchild", parent="child-1", stage=RevisionStage.LOGIC_REPAIR
        )
        snapshot = repository.append_revision(
            "job-1", grandchild, expected_version=snapshot.version
        )
        advanced = repository.promote_checkpoint(
            "job-1",
            Checkpoint.LOGIC_CERTIFIED,
            "grandchild",
            evidence_hash=make_revision("second", marker="second").code_hash,
            expected_version=snapshot.version,
        )
        assert advanced.logic_certified_revision_id == "grandchild"
    finally:
        repository.close()
