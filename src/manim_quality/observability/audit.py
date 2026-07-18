"""Structured, tamper-evident audit records with a persistence port."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from manim_quality.contracts._json_values import freeze_json_object, thaw_json_object
from manim_quality.delivery.evidence import content_hash

_FORBIDDEN_KEYS = frozenset(
    {"api_key", "authorization", "candidate_source", "prompt", "source_code"}
)
_MAX_PAYLOAD_BYTES = 65_536


class AuditConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    tenant_id: str
    job_id: str
    action: str
    outcome: str
    occurred_at: datetime
    actor: str
    revision_id: str | None
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in (
            "event_id",
            "tenant_id",
            "job_id",
            "action",
            "outcome",
            "actor",
        ):
            _text(getattr(self, name), name)
        if self.revision_id is not None:
            _text(self.revision_id, "revision_id")
        valid_time = isinstance(self.occurred_at, datetime)
        if not valid_time or self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        _reject_forbidden(self.payload)
        frozen = freeze_json_object(self.payload, "payload")
        encoded = json.dumps(
            thaw_json_object(frozen), sort_keys=True, separators=(",", ":")
        ).encode()
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            raise ValueError("audit payload exceeds size limit")
        object.__setattr__(self, "payload", frozen)

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "actor": self.actor,
            "event_id": self.event_id,
            "job_id": self.job_id,
            "occurred_at": self.occurred_at.isoformat(),
            "outcome": self.outcome,
            "payload": thaw_json_object(self.payload),
            "revision_id": self.revision_id,
            "tenant_id": self.tenant_id,
        }


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event: AuditEvent
    sequence: int
    previous_hash: str | None
    record_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.event, AuditEvent):
            raise TypeError("event must be AuditEvent")
        if not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("sequence must be positive")
        if self.previous_hash is not None:
            _hash(self.previous_hash, "previous_hash")
        _hash(self.record_hash, "record_hash")


class AuditRepository(Protocol):
    def get(self, event_id: str) -> AuditRecord | None: ...

    def last(self, tenant_id: str, job_id: str) -> AuditRecord | None: ...

    def append(self, record: AuditRecord) -> None: ...


class AuditTrail:
    def __init__(self, repository: AuditRepository) -> None:
        self._repository = repository

    def record(self, event: AuditEvent) -> AuditRecord:
        if not isinstance(event, AuditEvent):
            raise TypeError("event must be AuditEvent")
        existing = self._repository.get(event.event_id)
        if existing is not None:
            if existing.event != event:
                raise AuditConflict("audit event identity has different payload")
            return existing
        previous = self._repository.last(event.tenant_id, event.job_id)
        sequence = 1 if previous is None else previous.sequence + 1
        previous_hash = None if previous is None else previous.record_hash
        record = AuditRecord(
            event,
            sequence,
            previous_hash,
            _record_hash(event, sequence, previous_hash),
        )
        self._repository.append(record)
        return record


def verify_chain(records) -> bool:
    previous = None
    identity = None
    for expected_sequence, record in enumerate(records, start=1):
        if not isinstance(record, AuditRecord):
            return False
        expected_previous = None if previous is None else previous.record_hash
        event_identity = (record.event.tenant_id, record.event.job_id)
        identity = event_identity if identity is None else identity
        if (
            record.sequence != expected_sequence
            or event_identity != identity
            or record.previous_hash != expected_previous
            or record.record_hash
            != _record_hash(record.event, record.sequence, record.previous_hash)
        ):
            return False
        previous = record
    return True


def _record_hash(event: AuditEvent, sequence: int, previous_hash: str | None) -> str:
    return content_hash(
        {
            "event": event.to_dict(),
            "previous_hash": previous_hash,
            "sequence": sequence,
        }
    )


def _reject_forbidden(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValueError(f"forbidden audit payload field: {key}")
            _reject_forbidden(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden(item)


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _hash(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a canonical hash")
