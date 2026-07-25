"""Append-only rollback records for failed candidates."""

import sqlite3

from manim_quality.revisions.store import RollbackRecord


def record_rollback(
    connection: sqlite3.Connection,
    job_id: str,
    run_id: str,
    rollback_to_revision_id: str,
    failed_revision_id: str | None,
    reason_code: str,
    evidence_hash: str,
    job_version: int,
) -> None:
    connection.execute(
        """
        INSERT INTO quality_rollbacks (
            job_id, run_id, rollback_to_revision_id, failed_revision_id,
            reason_code, evidence_hash, job_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            run_id,
            rollback_to_revision_id,
            failed_revision_id,
            reason_code,
            evidence_hash,
            job_version,
        ),
    )


def list_rollbacks(
    connection: sqlite3.Connection, job_id: str
) -> tuple[RollbackRecord, ...]:
    rows = connection.execute(
        "SELECT * FROM quality_rollbacks WHERE job_id = ? ORDER BY job_version",
        (job_id,),
    ).fetchall()
    return tuple(
        RollbackRecord(
            row["job_id"],
            row["run_id"],
            row["rollback_to_revision_id"],
            row["failed_revision_id"],
            row["reason_code"],
            row["evidence_hash"],
            row["job_version"],
        )
        for row in rows
    )
