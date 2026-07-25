"""Narrow capabilities injected into queue execution."""

from typing import Protocol

from manim_quality.storage.queue_models import QueueItem

from .models import JobOutcome


class JobHandler(Protocol):
    def handle(self, item: QueueItem) -> JobOutcome: ...


class HoldHandler(Protocol):
    def hold(self, job_id: str, reason: str, stage_run_id: str) -> None: ...
