"""SQLite tenant-owned service-delivery reads."""

from __future__ import annotations

import json
from pathlib import Path

from ._sqlite import open_sqlite
from .errors import SubmissionNotFound


class SQLiteTenantReadRepository:
    def __init__(self, database: str | Path) -> None:
        self._connection = open_sqlite(database)

    def close(self) -> None:
        self._connection.close()

    def job(self, tenant_id: str, job_id: str) -> dict[str, object]:
        submission = self._owner(tenant_id, job_id)
        queue = self._connection.execute(
            "SELECT state, terminal_reason FROM quality_queue WHERE stage_run_id = ?",
            (submission["stage_run_id"],),
        ).fetchone()
        quality = self._connection.execute(
            "SELECT state FROM quality_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        run = self._connection.execute(
            "SELECT result_payload FROM quality_runs WHERE job_id = ? AND run_id = ?",
            (job_id, submission["stage_run_id"]),
        ).fetchone()
        return {
            "schema_version": 1,
            "job_id": job_id,
            "quality_state": None if quality is None else quality["state"],
            "queue_state": queue["state"],
            "terminal_reason": queue["terminal_reason"],
            "result": _result(run),
        }

    def revisions(self, tenant_id: str, job_id: str) -> list[dict[str, object]]:
        self._owner(tenant_id, job_id)
        rows = self._connection.execute(
            "SELECT payload FROM quality_revisions WHERE job_id = ? "
            "ORDER BY created_at, revision_id",
            (job_id,),
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def evidence_hashes(self, tenant_id: str, job_id: str) -> list[str]:
        self._owner(tenant_id, job_id)
        row = self._connection.execute(
            "SELECT render_baseline_evidence_hash, logic_certified_evidence_hash, "
            "layout_certified_evidence_hash, delivery_evidence_hash "
            "FROM quality_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return [] if row is None else [value for value in row if value is not None]

    def certificate(self, tenant_id: str, job_id: str) -> tuple[str, bytes] | None:
        self._owner(tenant_id, job_id)
        row = self._connection.execute(
            "SELECT q.delivery_evidence_hash, e.payload FROM quality_jobs q "
            "LEFT JOIN quality_evidence e ON "
            "e.evidence_hash = q.delivery_evidence_hash "
            "WHERE q.job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None or row["delivery_evidence_hash"] is None:
            return None
        return row["delivery_evidence_hash"], bytes(row["payload"])

    def _owner(self, tenant_id: str, job_id: str):
        row = self._connection.execute(
            "SELECT * FROM quality_submissions WHERE tenant_id = ? AND job_id = ?",
            (tenant_id, job_id),
        ).fetchone()
        if row is None:
            raise SubmissionNotFound(job_id)
        return row


def _result(row) -> dict[str, object] | None:
    if row is None or row["result_payload"] is None:
        return None
    return json.loads(row["result_payload"])
