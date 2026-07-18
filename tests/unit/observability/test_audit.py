from __future__ import annotations

from datetime import UTC, datetime

import pytest

from manim_quality.observability.audit import (
    AuditConflict,
    AuditEvent,
    AuditTrail,
    verify_chain,
)


def test_audit_records_form_tamper_evident_idempotent_chain() -> None:
    repository = MemoryAuditRepository()
    trail = AuditTrail(repository)
    first = _event("event-1", "quality_started")
    second = _event("event-2", "logic_reviewed")

    record_1 = trail.record(first)
    replay = trail.record(first)
    record_2 = trail.record(second)

    assert replay == record_1
    assert record_1.sequence == 1
    assert record_2.sequence == 2
    assert record_2.previous_hash == record_1.record_hash
    assert verify_chain(repository.records) is True


def test_event_identity_conflict_and_chain_tampering_fail_closed() -> None:
    repository = MemoryAuditRepository()
    trail = AuditTrail(repository)
    trail.record(_event("event-1", "quality_started"))

    with pytest.raises(AuditConflict, match="different payload"):
        trail.record(_event("event-1", "different_action"))
    forged = repository.records[0].__class__(
        repository.records[0].event,
        repository.records[0].sequence,
        repository.records[0].previous_hash,
        "sha256:" + "0" * 64,
    )
    assert verify_chain((forged,)) is False


@pytest.mark.parametrize(
    "key", ["api_key", "api-key", "authorization", "source_code", "prompt"]
)
def test_audit_rejects_sensitive_or_unbounded_payload_fields(key: str) -> None:
    with pytest.raises(ValueError, match="forbidden audit payload"):
        _event("event-1", "quality_started", payload={key: "secret"})


def test_chain_cannot_join_records_from_different_jobs() -> None:
    repository = MemoryAuditRepository()
    trail = AuditTrail(repository)
    first = trail.record(_event("event-1", "quality_started"))
    other_job = _event("event-2", "quality_started", job_id="job-2")
    forged = first.__class__(
        other_job,
        first.sequence + 1,
        first.record_hash,
        first.record_hash,
    )

    assert verify_chain((first, forged)) is False


class MemoryAuditRepository:
    def __init__(self) -> None:
        self.records = []

    def get(self, event_id: str):
        return next(
            (record for record in self.records if record.event.event_id == event_id),
            None,
        )

    def last(self, tenant_id: str, job_id: str):
        matches = [
            record
            for record in self.records
            if (record.event.tenant_id, record.event.job_id) == (tenant_id, job_id)
        ]
        return matches[-1] if matches else None

    def append(self, record) -> None:
        self.records.append(record)


def _event(
    event_id: str,
    action: str,
    *,
    job_id: str = "job-1",
    payload: dict[str, object] | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        tenant_id="tenant-a",
        job_id=job_id,
        action=action,
        outcome="SUCCESS",
        occurred_at=datetime(2026, 7, 12, tzinfo=UTC),
        actor="quality-platform",
        revision_id="revision-1",
        payload=payload or {"evidence_hash": "sha256:" + "1" * 64},
    )
