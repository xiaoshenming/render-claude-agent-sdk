"""Lease-fenced adapter from quality queue work to the orchestrator."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from manim_quality.orchestrator.models import ExecutionRequest, OrchestrationResult
from manim_quality.revisions.store import CommitFence
from manim_quality.storage.queue_models import QueueItem

from .models import JobOutcome


class QualityExecutionPort(Protocol):
    def execute(
        self,
        request: ExecutionRequest,
        *,
        commit_fence: CommitFence,
    ) -> OrchestrationResult: ...


class QualityRequestMismatch(ValueError):
    pass


class QualityJobHandler:
    def __init__(
        self,
        orchestrator: QualityExecutionPort,
        request_factory: Callable[[QueueItem], ExecutionRequest],
    ) -> None:
        self._orchestrator = orchestrator
        self._request_factory = request_factory

    def handle(self, item: QueueItem) -> JobOutcome:
        request = self._request_factory(item)
        _require_queue_identity(item, request)
        outcome = self._orchestrator.execute(
            request,
            commit_fence=CommitFence.from_queue_item(item),
        )
        callback_body = json.dumps(
            outcome.result.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return JobOutcome.completed(callback_body)


def _require_queue_identity(item: QueueItem, request: ExecutionRequest) -> None:
    if (
        request.job_id != item.job_id
        or request.run_id != item.stage_run_id
        or request.request_hash != item.request_hash
    ):
        raise QualityRequestMismatch(
            "quality request does not match claimed queue item"
        )
