from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from psycopg.errors import UniqueViolation

from apps.api.auth import GatewayHmacAuthenticator
from apps.api.main import ApiSettings, create_app
from apps.worker.main import WorkerSettings, create_worker
from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.storage.factory import StorageFactories, create_storage_factories
from manim_quality.storage.intake import IntakeLimits, IntakeTransactionError
from manim_quality.storage.postgres.common import canonical, queue_item
from manim_quality.storage.postgres.intake import PostgresIntakeRepository
from manim_quality.storage.postgres.queue import PostgresQueueRepository
from manim_quality.storage.postgres.reads import PostgresTenantReadRepository
from manim_quality.storage.postgres.replay import PostgresReplayRepository
from manim_quality.storage.queue import LeaseConflict
from manim_quality.storage.queue_models import (
    QueueClass,
    QueueState,
    SubmissionReceipt,
)
from tests.integration.test_api_jobs import submission
from tests.integration.test_worker_idempotency import utc


class Cursor:
    def __init__(self, rows=(), rowcount: int = 1) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return None if not self._rows else self._rows.pop(0)

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class Transaction:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        self.connection.events.append("BEGIN")
        return self

    def __exit__(self, error_type, error, traceback):
        self.connection.events.append("ROLLBACK" if error_type else "COMMIT")
        return False


class Connection:
    def __init__(self, responses=()) -> None:
        self.responses = list(responses)
        self.executed: list[tuple[str, object]] = []
        self.events: list[str] = []

    def transaction(self):
        return Transaction(self)

    def execute(self, sql: str, parameters=()):
        self.executed.append((" ".join(sql.split()), parameters))
        response = self.responses.pop(0) if self.responses else Cursor()
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


def queue_row() -> dict[str, object]:
    return {
        "stage_run_id": "quality:job-1:hash",
        "tenant_id": "tenant-a",
        "job_id": "job-1",
        "queue_class": "QUALITY",
        "state": "QUEUED",
        "payload": b"{}",
        "request_hash": "sha256:" + "a" * 64,
        "attempt": 0,
        "max_attempts": 3,
        "available_at": utc(),
        "deadline": utc(300),
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "terminal_reason": None,
        "callback_url": None,
    }
