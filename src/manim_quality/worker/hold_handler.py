"""Durable HOLD control-task adapter."""

import json

from manim_quality.storage.queue_models import QueueItem

from .models import JobOutcome
from .ports import HoldHandler


class HoldControlHandler:
    def __init__(self, handler: HoldHandler) -> None:
        self._handler = handler

    def handle(self, item: QueueItem) -> JobOutcome:
        payload = json.loads(item.payload)
        self._handler.hold(payload["job_id"], payload["reason"], item.stage_run_id)
        return JobOutcome.completed()
