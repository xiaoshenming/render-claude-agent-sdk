"""Callback delivery using injected DNS and HTTP capabilities."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from .security import ResolvedDestination, signature


class CallbackOutcome(StrEnum):
    DELIVERED = "DELIVERED"
    RETRY = "RETRY"


class CallbackTransport(Protocol):
    def send(
        self,
        destination: ResolvedDestination,
        body: bytes,
        headers: dict[str, str],
    ) -> int: ...


class CallbackDispatcher:
    def __init__(self, *, secret: bytes, key_id: str, resolver, transport) -> None:
        if not secret:
            raise ValueError("callback signing secret is required")
        if not key_id:
            raise ValueError("callback signing key_id is required")
        self._secret = secret
        self._key_id = key_id
        self._resolver = resolver
        self._transport = transport

    @staticmethod
    def sign(
        body: bytes,
        secret: bytes,
        key_id: str,
        event_id: str,
        delivery_id: str,
        now: datetime,
    ) -> dict[str, str]:
        timestamp = str(int(now.astimezone(UTC).timestamp()))
        return {
            "Content-Type": "application/json",
            "X-Quality-Timestamp": timestamp,
            "X-Quality-Event-Id": event_id,
            "X-Quality-Delivery-Id": delivery_id,
            "X-Quality-Key-Id": key_id,
            "X-Quality-Signature": signature(
                body, secret, timestamp, event_id, delivery_id
            ),
        }

    def deliver(
        self,
        url: str,
        body: bytes,
        *,
        now: datetime,
        event_id: str | None = None,
        delivery_id: str | None = None,
    ) -> CallbackOutcome:
        if not event_id:
            raise ValueError("callback event_id is required")
        if not delivery_id:
            raise ValueError("callback delivery_id is required")
        destination = ResolvedDestination.resolve(url, self._resolver)
        headers = self.sign(
            body, self._secret, self._key_id, event_id, delivery_id, now
        )
        status = self._transport.send(destination, body, headers)
        if 200 <= status < 300:
            return CallbackOutcome.DELIVERED
        return CallbackOutcome.RETRY
