"""Transactional PostgreSQL quality submission intake."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from psycopg import Error
from psycopg.errors import UniqueViolation

from manim_quality.contracts import QualitySubmission
from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.storage.errors import (
    IntakeConflict,
    IntakeQuotaExceeded,
    IntakeTransactionError,
)
from manim_quality.storage.queue_models import (
    IntakeLimits,
    QueueState,
    SubmissionReceipt,
)

from .common import canonical


class PostgresIntakeRepository:
    def __init__(self, connection_factory, publication_probe=None) -> None:
        self._connection_factory = connection_factory
        self._publication_probe = publication_probe

    def close(self) -> None:
        pass

    def submit(
        self,
        payload: Mapping[str, object],
        limits: IntakeLimits,
        *,
        max_attempts: int = 3,
        deadline_for: timedelta = timedelta(hours=2),
        now: datetime | None = None,
    ) -> SubmissionReceipt:
        submission = QualitySubmission.from_dict(dict(payload))
        body = canonical(submission.to_dict())
        request_hash = sha256_bytes(body)
        timestamp = now or datetime.now(UTC)
        run_id = f"quality:{submission.job_id}:{request_hash[7:23]}"
        connection = None
        try:
            connection = self._connection_factory()
            with connection.transaction():
                self._lock_tenant(connection, submission.tenant_id)
                existing = self._existing(connection, submission)
                if existing is not None:
                    return self._receipt(connection, existing, request_hash)
                self._require_available(connection, submission)
                self._require_quota(connection, submission.tenant_id, limits)
                self._insert_submission(
                    connection, submission, request_hash, run_id, body, timestamp
                )
                if self._publication_probe is not None:
                    self._publication_probe()
                self._insert_work(
                    connection,
                    submission,
                    request_hash,
                    run_id,
                    body,
                    max_attempts,
                    timestamp,
                    timestamp + deadline_for,
                )
            return SubmissionReceipt(submission.job_id, run_id, QueueState.QUEUED)
        except UniqueViolation:
            return self._resolve_unique_race(submission, request_hash)
        except Error as error:
            raise IntakeTransactionError(str(error)) from error
        finally:
            if connection is not None:
                connection.close()

    def _resolve_unique_race(self, submission, request_hash) -> SubmissionReceipt:
        connection = None
        try:
            connection = self._connection_factory()
            with connection.transaction():
                self._lock_tenant(connection, submission.tenant_id)
                existing = self._existing(connection, submission)
                if existing is None:
                    raise IntakeConflict("submission identity conflicts")
                return self._receipt(connection, existing, request_hash)
        except Error as error:
            raise IntakeTransactionError(str(error)) from error
        finally:
            if connection is not None:
                connection.close()

    def _existing(self, connection, submission):
        return connection.execute(
            "SELECT * FROM quality_submissions WHERE tenant_id = %s "
            "AND job_id = %s AND idempotency_key = %s FOR UPDATE",
            (submission.tenant_id, submission.job_id, submission.idempotency_key),
        ).fetchone()

    @staticmethod
    def _lock_tenant(connection, tenant_id: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (tenant_id,),
        )

    def _receipt(self, connection, row, request_hash) -> SubmissionReceipt:
        if row["request_hash"] != request_hash:
            raise IntakeConflict("submission identity conflicts")
        queue = connection.execute(
            "SELECT state FROM quality_queue WHERE stage_run_id = %s",
            (row["stage_run_id"],),
        ).fetchone()
        return SubmissionReceipt(
            row["job_id"], row["stage_run_id"], QueueState(queue["state"])
        )

    def _require_available(self, connection, submission) -> None:
        row = connection.execute(
            "SELECT 1 FROM quality_submissions WHERE job_id = %s OR "
            "(tenant_id = %s AND idempotency_key = %s) FOR UPDATE",
            (submission.job_id, submission.tenant_id, submission.idempotency_key),
        ).fetchone()
        if row is not None:
            raise IntakeConflict("submission identity conflicts")

    def _require_quota(self, connection, tenant_id, limits) -> None:
        row = connection.execute(
            "SELECT COUNT(*) FILTER (WHERE state IN ('QUEUED','RUNNING')) AS active, "
            "COUNT(*) FILTER (WHERE state = 'QUEUED') AS queued "
            "FROM quality_queue WHERE tenant_id = %s AND queue_class = 'QUALITY'",
            (tenant_id,),
        ).fetchone()
        if (
            row["active"] >= limits.max_active_jobs
            or row["queued"] >= limits.max_queued_jobs
        ):
            raise IntakeQuotaExceeded("tenant queue quota exceeded")

    def _insert_submission(
        self, connection, submission, request_hash, run_id, body, now
    ):
        connection.execute(
            "INSERT INTO quality_submissions (tenant_id, job_id, idempotency_key, "
            "request_hash, stage_run_id, payload, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                submission.tenant_id,
                submission.job_id,
                submission.idempotency_key,
                request_hash,
                run_id,
                body,
                now,
            ),
        )

    def _insert_work(
        self,
        connection,
        submission,
        request_hash,
        run_id,
        body,
        attempts,
        now,
        deadline,
    ):
        connection.execute(
            "INSERT INTO quality_queue (stage_run_id, tenant_id, job_id, queue_class, "
            "state, payload, request_hash, attempt, max_attempts, available_at, "
            "deadline, callback_url) VALUES "
            "(%s,%s,%s,'QUALITY','QUEUED',%s,%s,0,%s,%s,%s,%s)",
            (
                run_id,
                submission.tenant_id,
                submission.job_id,
                body,
                request_hash,
                attempts,
                now,
                deadline,
                submission.callback_url,
            ),
        )
