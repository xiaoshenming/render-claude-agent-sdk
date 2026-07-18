from pathlib import Path

import pytest

from manim_quality.contracts import (
    PatchScope,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.revisions.fingerprint import sha256_text
from manim_quality.revisions.store import RevisionNotFound, StaleWrite
from manim_quality.storage.database import SQLiteRevisionRepository


def revision(revision_id: str, parent: str | None = None) -> Revision:
    marker = revision_id
    return Revision(
        revision_id=revision_id,
        parent_revision_id=parent,
        stage=RevisionStage.BASELINE if parent is None else RevisionStage.LOGIC_REPAIR,
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


def test_two_sqlite_connections_reject_stale_worker(tmp_path: Path) -> None:
    database = tmp_path / "quality.sqlite3"
    first = SQLiteRevisionRepository(database)
    second = SQLiteRevisionRepository(database)
    try:
        first.create_job("job-1", revision("baseline"))
        first_snapshot = first.get_job("job-1")
        second_snapshot = second.get_job("job-1")

        current = first.append_revision(
            "job-1", revision("winner", "baseline"), expected_version=0
        )
        with pytest.raises(StaleWrite):
            second.append_revision(
                "job-1", revision("stale", "baseline"), expected_version=0
            )

        assert first_snapshot.version == second_snapshot.version == 0
        assert current.version == second.get_job("job-1").version == 1
        with pytest.raises(RevisionNotFound):
            first.get_revision("stale")
    finally:
        first.close()
        second.close()


def test_sqlite_adapter_enables_foreign_keys(tmp_path: Path) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    try:
        enabled = repository._connection.execute(  # type: ignore[attr-defined]
            "PRAGMA foreign_keys"
        ).fetchone()[0]
        assert enabled == 1
    finally:
        repository.close()
