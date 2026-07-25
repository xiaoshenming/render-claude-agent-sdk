"""Authenticated gateway tenant identity."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    tenant_id: str
    authenticated_at: datetime


class TenantAuthenticator(Protocol):
    def authenticate(self, headers: Mapping[str, str]) -> TenantPrincipal: ...


class GatewayHmacAuthenticator:
    def __init__(
        self,
        secret: bytes,
        *,
        max_age_seconds: int,
        clock=None,
    ) -> None:
        if not secret:
            raise ValueError("gateway secret is required")
        self._secret = secret
        self._max_age = max_age_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def headers(self, tenant_id: str, *, now: datetime | None = None) -> dict[str, str]:
        timestamp = str(int((now or self._clock()).timestamp()))
        return {
            "X-Gateway-Tenant": tenant_id,
            "X-Gateway-Timestamp": timestamp,
            "X-Gateway-Signature": self._sign(tenant_id, timestamp),
        }

    def authenticate(self, headers: Mapping[str, str]) -> TenantPrincipal:
        try:
            tenant_id = headers["x-gateway-tenant"]
            timestamp_text = headers["x-gateway-timestamp"]
            supplied = headers["x-gateway-signature"]
            timestamp = datetime.fromtimestamp(int(timestamp_text), UTC)
        except (KeyError, ValueError, OverflowError) as error:
            raise AuthenticationError("invalid gateway authentication") from error
        now = self._clock().astimezone(UTC)
        if not tenant_id or abs((now - timestamp).total_seconds()) > self._max_age:
            raise AuthenticationError("invalid gateway authentication")
        expected = self._sign(tenant_id, timestamp_text)
        if not hmac.compare_digest(supplied, expected):
            raise AuthenticationError("invalid gateway authentication")
        return TenantPrincipal(tenant_id, timestamp)

    def _sign(self, tenant_id: str, timestamp: str) -> str:
        payload = f"{timestamp}.{tenant_id}".encode()
        return "sha256=" + hmac.new(self._secret, payload, "sha256").hexdigest()
