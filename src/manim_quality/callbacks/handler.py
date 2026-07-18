"""Callback queue handler built from the secure dispatcher."""

from manim_quality.storage.queue_models import QueueItem
from manim_quality.worker.models import JobOutcome

from .delivery import CallbackDispatcher, CallbackOutcome


class CallbackDeliveryError(RuntimeError):
    pass


class CallbackJobHandler:
    def __init__(self, dispatcher: CallbackDispatcher) -> None:
        self._dispatcher = dispatcher

    def handle(self, item: QueueItem) -> JobOutcome:
        if item.callback_url is None:
            raise CallbackDeliveryError("callback task has no destination")
        now = item.heartbeat_at
        if now is None:
            raise CallbackDeliveryError("callback task has no lease heartbeat")
        outcome = self._dispatcher.deliver(
            item.callback_url,
            item.payload,
            now=now,
            event_id=item.stage_run_id,
            delivery_id=f"{item.stage_run_id}:{item.attempt}",
        )
        if outcome is not CallbackOutcome.DELIVERED:
            raise CallbackDeliveryError("callback endpoint requested retry")
        return JobOutcome.completed()
