"""Transactional quality submission intake and tenant-scoped reads."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from manim_quality.contracts import QualitySubmission
from manim_quality.revisions.fingerprint import sha256_bytes

from ._sqlite import open_sqlite, transaction
from .errors import (
    IntakeConflict,
    IntakeQuotaExceeded,
    IntakeTransactionError,
    SubmissionNotFound,
)
from .queue_models import IntakeLimits, QueueState, SubmissionReceipt

__all__ = [
    "IntakeConflict",
    "IntakeQuotaExceeded",
    "IntakeTransactionError",
    "SQLiteIntakeRepository",
    "SubmissionNotFound",
]


class SQLiteIntakeRepository:
    def __init__(
        self,
        database: str | Path,
        publication_probe: Callable[[], None] | None = None,
    ) -> None:
        self._connection = open_sqlite(database)
        self._publication_probe = publication_probe

    def close(self) -> None:
        self._connection.close()

    def submit(
        self,
        payload: Mapping[str, object],
        limits: IntakeLimits,
        *,
        max_attempts: int = 3,
        deadline_for: timedelta = timedelta(hours=2),
        now: datetime | None = None,
    ) -> SubmissionReceipt:
        if deadline_for <= timedelta(0):
            raise ValueError("deadline_for must be positive")
        submission = QualitySubmission.from_dict(dict(payload))
        body = _canonical(submission.to_dict())
        request_hash = sha256_bytes(body)
        timestamp = now or datetime.now(UTC)
        stage_run_id = f"quality:{submission.job_id}:{request_hash[7:23]}"
        with transaction(self._connection):
            existing = self._find_identity(submission)
            if existing is not None:
                return self._idempotent(existing, request_hash)
            self._check_conflicts(submission)
            self._check_quota(submission.tenant_id, limits)
            self._insert_submission(submission, request_hash, body, timestamp)
            if self._publication_probe is not None:
                self._publication_probe()
            self._insert_work(
                submission,
                stage_run_id,
                request_hash,
                body,
                max_attempts,
                deadline_for,
                timestamp,
            )
        return SubmissionReceipt(submission.job_id, stage_run_id, QueueState.QUEUED)

    def get(self, tenant_id: str, job_id: str):
        row = self._connection.execute(
            "SELECT * FROM quality_submissions WHERE tenant_id = ? AND job_id = ?",
            (tenant_id, job_id),
        ).fetchone()
        if row is None:
            raise SubmissionNotFound(job_id)
        queue = self._connection.execute(
            "SELECT state, terminal_reason FROM quality_queue WHERE stage_run_id = ?",
            (row["stage_run_id"],),
        ).fetchone()
        return row, queue

    def _find_identity(self, submission: QualitySubmission):
        return self._connection.execute(
            "SELECT * FROM quality_submissions "
            "WHERE tenant_id = ? AND job_id = ? AND idempotency_key = ?",
            (submission.tenant_id, submission.job_id, submission.idempotency_key),
        ).fetchone()

    def _idempotent(self, row, request_hash: str) -> SubmissionReceipt:
        if row["request_hash"] != request_hash:
            raise IntakeConflict("idempotency identity has a different payload")
        queue = self._connection.execute(
            "SELECT state FROM quality_queue WHERE stage_run_id = ?",
            (row["stage_run_id"],),
        ).fetchone()
        return SubmissionReceipt(
            row["job_id"], row["stage_run_id"], QueueState(queue["state"])
        )

    def _check_conflicts(self, submission: QualitySubmission) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM quality_submissions WHERE job_id = ? OR "
            "(tenant_id = ? AND idempotency_key = ?)",
            (submission.job_id, submission.tenant_id, submission.idempotency_key),
        ).fetchone()
        if row is not None:
            raise IntakeConflict("job_id or idempotency_key already exists")

    def _check_quota(self, tenant_id: str, limits: IntakeLimits) -> None:
        active = self._connection.execute(
            "SELECT COUNT(*) FROM quality_queue WHERE tenant_id = ? "
            "AND queue_class = 'QUALITY' AND state IN ('QUEUED', 'RUNNING')",
            (tenant_id,),
        ).fetchone()[0]
        queued = self._connection.execute(
            "SELECT COUNT(*) FROM quality_queue WHERE tenant_id = ? "
            "AND queue_class = 'QUALITY' AND state = 'QUEUED'",
            (tenant_id,),
        ).fetchone()[0]
        if active >= limits.max_active_jobs or queued >= limits.max_queued_jobs:
            raise IntakeQuotaExceeded("tenant queue quota exceeded")

    def _insert_submission(self, submission, request_hash, body, now) -> None:
        self._connection.execute(
            "INSERT INTO quality_submissions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                submission.tenant_id,
                submission.job_id,
                submission.idempotency_key,
                request_hash,
                f"quality:{submission.job_id}:{request_hash[7:23]}",
                body,
                _iso(now),
            ),
        )

    def _insert_work(
        self, submission, run_id, request_hash, body, attempts, deadline_for, now
    ):
        self._connection.execute(
            "INSERT INTO quality_queue (stage_run_id, tenant_id, job_id, queue_class, "
            "state, payload, request_hash, attempt, max_attempts, available_at, "
            "deadline, "
            "callback_url) VALUES (?, ?, ?, 'QUALITY', 'QUEUED', ?, ?, 0, ?, ?, ?, ?)",
            (
                run_id,
                submission.tenant_id,
                submission.job_id,
                body,
                request_hash,
                attempts,
                _iso(now),
                _iso(now + deadline_for),
                submission.callback_url,
            ),
        )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
