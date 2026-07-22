from __future__ import annotations

import inspect
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from manim_quality.revisions.store import StaleWrite, TransitionReplayAdvanced
from manim_quality.storage.intake import IntakeLimits, SQLiteIntakeRepository
from manim_quality.storage.queue import (
    LeaseConflict,
    QueueClass,
    QueueState,
    SQLiteQueueRepository,
)

from .test_api_jobs import submission


def utc(second: int = 0) -> datetime:
    return datetime(2026, 7, 11, 8, 0, tzinfo=UTC) + timedelta(seconds=second)


def seeded_repository(
    tmp_path: Path,
    *,
    attempts: int = 3,
    deadline_for: timedelta = timedelta(hours=2),
) -> SQLiteQueueRepository:
    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(),
        IntakeLimits(),
        max_attempts=attempts,
        deadline_for=deadline_for,
        now=utc(),
    )
    return SQLiteQueueRepository(database)


@dataclass
class Handler:
    outcomes: list[object]
    calls: list[str] = field(default_factory=list)

    def handle(self, item):
        self.calls.append(item.stage_run_id)
        value = self.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@dataclass
class Holds:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def hold(self, job_id: str, reason: str, stage_run_id: str = "test") -> None:
        self.calls.append((job_id, reason))
def test_expired_quality_lease_cannot_persist_terminal_result(tmp_path: Path) -> None:
    from dataclasses import replace

    from manim_quality.orchestrator.models import StageAction
    from manim_quality.revisions.store import CommitFence, CommitFenceRejected
    from manim_quality.storage.database import SQLiteRevisionRepository
    from tests.e2e.test_quality_happy_path import (
        baseline,
        execution_request,
        service,
    )

    database = tmp_path / "quality.sqlite3"
    now = datetime.now(UTC)
    SQLiteIntakeRepository(database).submit(
        submission(),
        IntakeLimits(),
        deadline_for=timedelta(milliseconds=50),
        now=now,
    )
    queue = SQLiteQueueRepository(database)
    lease = queue.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=now,
        lease_for=timedelta(seconds=1),
    )
    assert lease is not None
    revisions = SQLiteRevisionRepository(database)
    revisions.create_job("job-1", baseline())
    request = replace(
        execution_request(), run_id=lease.stage_run_id, request_hash=lease.request_hash
    )

    time.sleep(0.08)
    with pytest.raises(CommitFenceRejected):
        service(revisions, StageAction.CLEAN, StageAction.CLEAN).execute(
            request, commit_fence=CommitFence.from_queue_item(lease)
        )

    assert (
        revisions.get_run_result("job-1", request.run_id, request.request_hash) is None
    )
def test_reclaimed_quality_lease_rejects_old_worker_terminal_result(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from manim_quality.orchestrator.models import StageAction
    from manim_quality.revisions.store import CommitFence, CommitFenceRejected
    from manim_quality.storage.database import SQLiteRevisionRepository
    from tests.e2e.test_quality_happy_path import (
        baseline,
        execution_request,
        service,
    )

    database = tmp_path / "quality.sqlite3"
    now = datetime.now(UTC)
    SQLiteIntakeRepository(database).submit(
        submission(), IntakeLimits(), deadline_for=timedelta(hours=1), now=now
    )
    queue = SQLiteQueueRepository(database)
    old_lease = queue.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=now,
        lease_for=timedelta(milliseconds=50),
    )
    assert old_lease is not None
    replacement = queue.claim(
        QueueClass.QUALITY,
        "worker-b",
        now=now + timedelta(milliseconds=60),
        lease_for=timedelta(seconds=1),
    )
    assert replacement is not None
    revisions = SQLiteRevisionRepository(database)
    revisions.create_job("job-1", baseline())
    request = replace(
        execution_request(),
        run_id=old_lease.stage_run_id,
        request_hash=old_lease.request_hash,
    )

    with pytest.raises(CommitFenceRejected):
        service(revisions, StageAction.CLEAN, StageAction.CLEAN).execute(
            request, commit_fence=CommitFence.from_queue_item(old_lease)
        )

    assert (
        revisions.get_run_result("job-1", request.run_id, request.request_hash) is None
    )
def test_quality_worker_threads_claimed_fence_into_orchestrator(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from apps.worker.main import WorkerSettings, create_quality_worker
    from manim_quality.contracts import DeliveryDecision, QualityResult
    from manim_quality.orchestrator.models import OrchestrationResult
    from tests.e2e.test_quality_happy_path import execution_request

    repository = seeded_repository(tmp_path)
    observed = []

    class Orchestrator:
        def execute(self, request, *, commit_fence):
            observed.append((request, commit_fence))
            return OrchestrationResult(
                QualityResult(
                    request.job_id,
                    DeliveryDecision.HOLD,
                    None,
                    None,
                    None,
                    None,
                    (),
                    {},
                    {},
                ),
                object(),
            )

    def request_factory(item):
        return replace(
            execution_request(),
            run_id=item.stage_run_id,
            request_hash=item.request_hash,
        )

    worker = create_quality_worker(
        repository,
        Orchestrator(),
        request_factory,
        Holds(),
        WorkerSettings(),
    )

    assert worker.run_once("worker-a", now=utc()) is True
    request, fence = observed[0]
    completed = repository.get(request.run_id)

    assert fence.stage_run_id == request.run_id
    assert fence.lease_owner == "worker-a"
    assert fence.lease_token is not None
    assert fence.deadline == completed.deadline
