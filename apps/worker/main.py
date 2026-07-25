"""Worker factory; imports do not open databases or start loops."""

import socket
import ssl

from manim_quality.callbacks.delivery import CallbackDispatcher
from manim_quality.callbacks.handler import CallbackJobHandler
from manim_quality.callbacks.pinned_transport import PinnedHttpTransport
from manim_quality.storage.ports import QueueRepository
from manim_quality.storage.queue_models import QueueClass
from manim_quality.worker.hold_handler import HoldControlHandler
from manim_quality.worker.ports import HoldHandler, JobHandler
from manim_quality.worker.quality_handler import (
    QualityExecutionPort,
    QualityJobHandler,
)
from manim_quality.worker.service import QueueWorker, WorkerSettings


def create_worker(
    repository: QueueRepository,
    handler: JobHandler,
    hold_handler: HoldHandler,
    settings: WorkerSettings,
) -> QueueWorker:
    return QueueWorker(repository, handler, hold_handler, settings)


def create_quality_worker(
    repository: QueueRepository,
    orchestrator: QualityExecutionPort,
    request_factory,
    hold_handler: HoldHandler,
    settings: WorkerSettings,
) -> QueueWorker:
    if settings.queue_class is not QueueClass.QUALITY:
        raise ValueError("quality worker requires QUALITY queue class")
    return QueueWorker(
        repository,
        QualityJobHandler(orchestrator, request_factory),
        hold_handler,
        settings,
    )


def create_callback_worker(
    repository: QueueRepository,
    *,
    secret: bytes,
    key_id: str,
    resolver,
    settings: WorkerSettings,
    socket_factory=socket.create_connection,
    ssl_context: ssl.SSLContext | None = None,
    timeout_seconds: float = 10,
) -> QueueWorker:
    if settings.queue_class is not QueueClass.CALLBACK:
        raise ValueError("callback worker requires CALLBACK queue class")
    transport = PinnedHttpTransport(
        socket_factory=socket_factory,
        ssl_context=ssl_context,
        timeout_seconds=timeout_seconds,
    )
    dispatcher = CallbackDispatcher(
        secret=secret,
        key_id=key_id,
        resolver=resolver,
        transport=transport,
    )
    return QueueWorker(
        repository,
        CallbackJobHandler(dispatcher),
        None,
        settings,
    )


def create_hold_worker(
    repository: QueueRepository,
    hold_handler: HoldHandler,
    settings: WorkerSettings,
) -> QueueWorker:
    hold_settings = WorkerSettings(
        queue_class=QueueClass.HOLD,
        lease_for=settings.lease_for,
        base_backoff=settings.base_backoff,
        heartbeat_interval=settings.heartbeat_interval,
    )
    return QueueWorker(
        repository, HoldControlHandler(hold_handler), None, hold_settings
    )


__all__ = [
    "WorkerSettings",
    "create_callback_worker",
    "create_hold_worker",
    "create_quality_worker",
    "create_worker",
]
