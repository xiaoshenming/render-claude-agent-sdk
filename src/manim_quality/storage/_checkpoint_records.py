"""Append-only SQLite records for checkpoint evidence."""

import sqlite3

from manim_quality.revisions.store import Checkpoint


def record_checkpoint(
    connection: sqlite3.Connection,
    job_id: str,
    checkpoint: Checkpoint,
    revision_id: str,
    evidence_hash: str,
    *,
    version: int,
) -> None:
    connection.execute(
        """
        INSERT INTO quality_checkpoint_history (
            job_id, checkpoint, revision_id, evidence_hash, job_version
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (job_id, checkpoint.name, revision_id, evidence_hash, version),
    )
