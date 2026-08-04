"""Durable per-call usage ledger and job-level receipt aggregation."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .usage import AgentCallRecord, TokenUsage, UsageSink


@dataclass(frozen=True, slots=True)
class JobUsageReceipt:
    job_id: str
    calls: int
    usage: TokenUsage
    elapsed_ms: int
    external_tool_ms: int
    usage_complete: bool
    record_hashes: tuple[str, ...]


def aggregate_job_usage(
    job_id: str,
    records: Sequence[AgentCallRecord],
) -> JobUsageReceipt:
    usage = TokenUsage()
    for record in records:
        usage = usage.plus(record.usage)
    return JobUsageReceipt(
        job_id=job_id,
        calls=len(records),
        usage=usage,
        elapsed_ms=sum(record.elapsed_ms for record in records),
        external_tool_ms=sum(record.external_tool_ms for record in records),
        usage_complete=all(record.usage_complete for record in records),
        record_hashes=tuple(_record_hash(record) for record in records),
    )


class JsonlUsageLedger(UsageSink):
    """Append one fsync'd and process-safe record per completed Agent call."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, record: AgentCallRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _record_payload(record)
        with self.path.open("a", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                stream.write(json.dumps(
                    payload, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class RecordingJsonlUsageLedger(JsonlUsageLedger):
    """Persist calls immediately and retain them for the process summary."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        super().save(record)
        self.records.append(record)


def _record_payload(record: AgentCallRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "role": record.role,
        "model": record.model,
        "prompt_version": record.prompt_version,
        "schema_version": record.schema_version,
        "tool_version": record.tool_version,
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_read_tokens": record.usage.cache_read_tokens,
            "cache_write_tokens": record.usage.cache_write_tokens,
        },
        "turns": record.turns,
        "observed_model_rounds": record.observed_model_rounds,
        "elapsed_ms": record.elapsed_ms,
        "external_tool_ms": record.external_tool_ms,
        "usage_complete": record.usage_complete,
        "token_limit_observations": list(record.token_limit_observations),
        "tool_calls": [
            {
                "name": call.name,
                "caller": call.caller,
                "agent_id": call.agent_id,
                "duration_ms": call.duration_ms,
                "result_status": call.result_status,
            }
            for call in record.tool_calls
        ],
        "error": record.error,
    }


def _record_hash(record: AgentCallRecord) -> str:
    raw = json.dumps(_record_payload(record), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
