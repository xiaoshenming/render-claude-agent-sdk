"""Concurrent fake quality-queue load test with a durable JSON result."""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from manim_quality.storage.intake import SQLiteIntakeRepository
from manim_quality.storage.queue import SQLiteQueueRepository
from manim_quality.storage.queue_models import IntakeLimits, QueueClass, QueueState
from manim_quality.worker.models import JobOutcome
from manim_quality.worker.service import QueueWorker, WorkerSettings


@dataclass(frozen=True, slots=True)
class LoadReport:
    submitted: int
    completed: int
    dead_letter: int
    handler_calls: int
    duplicate_completions: int
    duration_ms: int
    workers: int


class _Handler:
    def __init__(self) -> None:
        self._calls: Counter[str] = Counter()
        self._lock = threading.Lock()

    def handle(self, item) -> JobOutcome:
        with self._lock:
            self._calls[item.job_id] += 1
        return JobOutcome.completed(b'{"state":"FAKE_RENDERED"}')

    @property
    def calls(self) -> Counter[str]:
        with self._lock:
            return self._calls.copy()


def run_fake_load(database: Path, *, jobs: int, workers: int) -> LoadReport:
    _positive(jobs, "jobs")
    _positive(workers, "workers")
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(lambda index: _submit(database, index, jobs), range(jobs)))
    handler = _Handler()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(
            executor.map(lambda index: _drain(database, handler, index), range(workers))
        )
    repository = SQLiteQueueRepository(database)
    try:
        items = repository.list_items(QueueClass.QUALITY)
    finally:
        repository.close()
    counts = Counter(item.state for item in items)
    calls = handler.calls
    return LoadReport(
        submitted=len(items),
        completed=counts[QueueState.COMPLETED],
        dead_letter=counts[QueueState.DEAD_LETTER],
        handler_calls=sum(calls.values()),
        duplicate_completions=sum(value - 1 for value in calls.values() if value > 1),
        duration_ms=max(1, int((time.monotonic() - started) * 1_000)),
        workers=workers,
    )


def _submit(database: Path, index: int, total: int) -> None:
    repository = SQLiteIntakeRepository(database)
    try:
        repository.submit(
            _submission(index),
            IntakeLimits(max_active_jobs=total + 1, max_queued_jobs=total + 1),
            deadline_for=timedelta(minutes=10),
        )
    finally:
        repository.close()


def _drain(database: Path, handler: _Handler, index: int) -> None:
    repository = SQLiteQueueRepository(database)
    worker = QueueWorker(
        repository,
        handler,
        None,
        WorkerSettings(
            lease_for=timedelta(seconds=30),
            heartbeat_interval=timedelta(seconds=5),
        ),
    )
    try:
        while worker.run_once(f"load-worker-{index}"):
            pass
    finally:
        repository.close()


def _submission(index: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": f"load-job-{index:04d}",
        "tenant_id": "load-test",
        "candidate_code_ref": f"artifact://candidate-{index:04d}.py",
        "problem_text": "Load-test problem.",
        "planning": {"scenes": ["ProofScene"]},
        "expected_answer": None,
        "render_manifest_ref": f"artifact://render-{index:04d}.json",
        "asset_manifest_ref": None,
        "callback_url": None,
        "idempotency_key": f"load-idem-{index:04d}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_fake_load(args.database, jobs=args.jobs, workers=args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"load: submitted={report.submitted} completed={report.completed} "
        f"duplicates={report.duplicate_completions} duration_ms={report.duration_ms}"
    )
    return 0 if report.completed == report.submitted else 1


def _positive(value: object, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be positive")


if __name__ == "__main__":
    raise SystemExit(main())
