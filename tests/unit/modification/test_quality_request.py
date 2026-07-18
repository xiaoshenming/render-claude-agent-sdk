from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from manim_quality.modification.approval import build_approval
from manim_quality.modification.quality_request import execution_request_from_queue
from manim_quality.storage.queue_models import QueueClass, QueueItem, QueueState
from tests.e2e.test_modification_preview_publish import _context, _draft


def test_approved_payload_builds_worker_execution_request() -> None:
    command = build_approval(_context().quality_request, _draft())
    item = _item(command)

    request = execution_request_from_queue(item)

    assert request.job_id == command.quality_job_id
    assert request.run_id == command.stage_run_id
    assert request.request_hash == command.request_hash
    assert request.source_code == _draft().candidate_source


def test_worker_parser_rejects_queue_identity_mismatch() -> None:
    command = build_approval(_context().quality_request, _draft())
    item = _item(command, job_id="another-job")

    with pytest.raises(ValueError, match="identity mismatch"):
        execution_request_from_queue(item)


def _item(command, *, job_id: str | None = None) -> QueueItem:
    now = datetime(2026, 7, 12, tzinfo=UTC)
    return QueueItem(
        command.stage_run_id,
        "tenant-a",
        job_id or command.quality_job_id,
        QueueClass.QUALITY,
        QueueState.QUEUED,
        command.payload,
        command.request_hash,
        0,
        3,
        now,
        now + timedelta(hours=2),
    )
