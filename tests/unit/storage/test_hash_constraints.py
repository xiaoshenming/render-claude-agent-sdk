import sqlite3
from pathlib import Path

import pytest

from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import baseline


@pytest.mark.parametrize(
    "invalid_hash",
    [
        "sha256:" + "G" * 64,
        "sha256:" + "z" * 64,
        "SHA256:" + "a" * 64,
    ],
)
def test_sqlite_rejects_noncanonical_71_character_hashes(
    tmp_path: Path, invalid_hash: str
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    try:
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(  # type: ignore[attr-defined]
                "UPDATE quality_jobs SET render_baseline_evidence_hash = ? "
                "WHERE job_id = 'job-1'",
                (invalid_hash,),
            )
    finally:
        repository.close()
