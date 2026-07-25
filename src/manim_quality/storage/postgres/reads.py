"""PostgreSQL tenant-owned quality reads."""

import json

from manim_quality.storage.errors import SubmissionNotFound


class PostgresTenantReadRepository:
    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def close(self) -> None:
        pass

    def job(self, tenant_id: str, job_id: str) -> dict[str, object]:
        connection = self._connection_factory()
        try:
            owner = self._owner(connection, tenant_id, job_id)
            queue = connection.execute(
                "SELECT state, terminal_reason FROM quality_queue "
                "WHERE stage_run_id=%s",
                (owner["stage_run_id"],),
            ).fetchone()
            quality = connection.execute(
                "SELECT state FROM quality_jobs WHERE job_id=%s", (job_id,)
            ).fetchone()
            run = connection.execute(
                "SELECT result_payload FROM quality_runs WHERE job_id=%s AND run_id=%s",
                (job_id, owner["stage_run_id"]),
            ).fetchone()
            return {
                "schema_version": 1,
                "job_id": job_id,
                "quality_state": None if quality is None else quality["state"],
                "queue_state": queue["state"],
                "terminal_reason": queue["terminal_reason"],
                "result": _result(run),
            }
        finally:
            connection.close()

    def revisions(self, tenant_id: str, job_id: str) -> list[dict[str, object]]:
        connection = self._connection_factory()
        try:
            self._owner(connection, tenant_id, job_id)
            rows = connection.execute(
                "SELECT payload FROM quality_revisions WHERE job_id=%s "
                "ORDER BY created_at, revision_id",
                (job_id,),
            ).fetchall()
            return [
                row["payload"]
                if isinstance(row["payload"], dict)
                else json.loads(row["payload"])
                for row in rows
            ]
        finally:
            connection.close()

    def evidence_hashes(self, tenant_id: str, job_id: str) -> list[str]:
        connection = self._connection_factory()
        try:
            self._owner(connection, tenant_id, job_id)
            row = connection.execute(
                "SELECT render_baseline_evidence_hash, logic_certified_evidence_hash, "
                "layout_certified_evidence_hash, delivery_evidence_hash "
                "FROM quality_jobs WHERE job_id=%s",
                (job_id,),
            ).fetchone()
            return [] if row is None else [value for value in row.values() if value]
        finally:
            connection.close()

    def certificate(self, tenant_id: str, job_id: str) -> tuple[str, bytes] | None:
        connection = self._connection_factory()
        try:
            self._owner(connection, tenant_id, job_id)
            row = connection.execute(
                "SELECT q.delivery_evidence_hash, e.payload FROM quality_jobs q "
                "LEFT JOIN quality_evidence e ON "
                "e.evidence_hash=q.delivery_evidence_hash "
                "WHERE q.job_id=%s",
                (job_id,),
            ).fetchone()
            if row is None or row["delivery_evidence_hash"] is None:
                return None
            return row["delivery_evidence_hash"], bytes(row["payload"])
        finally:
            connection.close()

    @staticmethod
    def _owner(connection, tenant_id: str, job_id: str):
        row = connection.execute(
            "SELECT * FROM quality_submissions WHERE tenant_id=%s AND job_id=%s",
            (tenant_id, job_id),
        ).fetchone()
        if row is None:
            raise SubmissionNotFound(job_id)
        return row


def _result(row):
    if row is None or row["result_payload"] is None:
        return None
    payload = row["result_payload"]
    return payload if isinstance(payload, dict) else json.loads(payload)
