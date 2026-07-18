"""Callback destination and signature verification primitives."""

from __future__ import annotations

import hmac
import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from manim_quality.storage.replay import ReplayRepository


class CallbackSecurityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedDestination:
    url: str
    hostname: str
    addresses: tuple[str, ...]

    @classmethod
    def resolve(cls, url: str, resolver) -> ResolvedDestination:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise CallbackSecurityError("callback scheme must be http or https")
        if parsed.username is not None or parsed.password is not None:
            raise CallbackSecurityError("callback URL userinfo is forbidden")
        if parsed.hostname is None or parsed.hostname.lower() == "localhost":
            raise CallbackSecurityError("callback hostname is forbidden")
        try:
            addresses = tuple(resolver(parsed.hostname))
        except Exception as error:
            raise CallbackSecurityError("callback DNS resolution failed") from error
        if not addresses:
            raise CallbackSecurityError("callback DNS returned no addresses")
        for address in addresses:
            try:
                parsed_ip = ipaddress.ip_address(address)
            except ValueError as error:
                raise CallbackSecurityError(
                    "callback DNS returned invalid IP"
                ) from error
            if not parsed_ip.is_global:
                raise CallbackSecurityError("callback address is not globally routable")
        return cls(url, parsed.hostname, addresses)


def verify_callback_signature(
    body: bytes,
    headers: dict[str, str],
    keys: dict[str, bytes],
    now: datetime,
    replay_repository: ReplayRepository,
    *,
    tolerance: timedelta = timedelta(minutes=5),
) -> None:
    try:
        timestamp_text = headers["X-Quality-Timestamp"]
        event_id = headers["X-Quality-Event-Id"]
        delivery_id = headers["X-Quality-Delivery-Id"]
        key_id = headers["X-Quality-Key-Id"]
        signature = headers["X-Quality-Signature"]
        timestamp = datetime.fromtimestamp(int(timestamp_text), UTC)
        secret = keys[key_id]
    except (KeyError, ValueError, OverflowError) as error:
        raise CallbackSecurityError("invalid callback signature headers") from error
    if abs(now.astimezone(UTC) - timestamp) > tolerance:
        raise CallbackSecurityError("callback timestamp outside tolerance")
    expected = _signature(body, secret, timestamp_text, event_id, delivery_id)
    if not hmac.compare_digest(signature, expected):
        raise CallbackSecurityError("invalid callback signature")
    if not replay_repository.claim(
        delivery_id, expires_at=timestamp + tolerance, now=now.astimezone(UTC)
    ):
        raise CallbackSecurityError("callback delivery replayed")


def _signature(
    body: bytes,
    secret: bytes,
    timestamp: str,
    event_id: str,
    delivery_id: str,
) -> str:
    signed = (
        timestamp.encode()
        + b"."
        + event_id.encode()
        + b"."
        + delivery_id.encode()
        + b"."
        + body
    )
    return "sha256=" + hmac.new(secret, signed, "sha256").hexdigest()


def signature(
    body: bytes,
    secret: bytes,
    timestamp: str,
    event_id: str,
    delivery_id: str,
) -> str:
    return _signature(body, secret, timestamp, event_id, delivery_id)
