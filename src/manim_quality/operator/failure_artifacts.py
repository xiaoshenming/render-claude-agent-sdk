"""Partial evidence pack for interrupted Quality Agent runs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object

from .artifacts import (
    _agent_call,
    _usage,
    _validate_existing_root,
    _write_inputs,
    _write_json,
    _write_jsonl,
    _write_revisions,
    _write_text,
)
from .session import QualitySession


def write_failed_run_artifacts(
    *,
    root: Path,
    session: QualitySession,
    record,
    baseline_layout_report: Mapping[str, object],
    error: Exception,
) -> None:
    target = Path(root)
    _validate_existing_root(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("input", "revisions", "evidence", "logs", "output"):
        (target / name).mkdir(exist_ok=True)
    _write_inputs(target, session)
    _write_revisions(target, session)
    _write_json(
        target / "evidence" / "layout.R0.baseline.json",
        thaw_json_object(baseline_layout_report),
    )
    _write_json(target / "logs" / "agent_call.partial.json", _agent_call(record))
    _write_jsonl(
        target / "logs" / "tool_calls.jsonl",
        [_tool_call(item) for item in record.tool_calls],
    )
    _write_jsonl(target / "logs" / "parent-sdk-messages.jsonl", [])
    _write_json(target / "logs" / "subagent-results.json", {"results": []})
    failure = _failure(record, session, error)
    _write_json(target / "logs" / "failure.json", failure)
    _write_json(target / "output" / "decision.json", {"decision": "FAILED", **failure})
    _write_text(
        target / "output" / f"latest_validated.{session.current_revision.revision_id}.py",
        session.current_revision.code,
    )


def _tool_call(item) -> dict[str, object]:
    return {
        "name": item.name,
        "input": thaw_json_object(item.input),
        "allowed": item.allowed,
        "error": item.error,
        "result_status": item.result_status,
        "result_hash": item.result_hash,
        "caller": item.caller,
        "agent_id": item.agent_id,
        "agent_type": item.agent_type,
    }


def _failure(record, session: QualitySession, error: Exception) -> dict[str, object]:
    return {
        "status": _failure_status(record.error or str(error), session),
        "error_type": type(error).__name__,
        "error": str(error),
        "last_revision_id": session.current_revision.revision_id,
        "last_revision_code_hash": session.current_revision.code_hash,
        "submitted_revision_id": session.submitted_revision_id,
        "tokens": _usage(record.usage),
        "turns": record.turns,
        "tool_calls": len(record.tool_calls),
    }


def _failure_status(error: str, session: QualitySession) -> str:
    text = error.lower()
    if session.submitted_revision_id and ("structured" in text or "output" in text):
        return "FAILED_STRUCTURED_OUTPUT"
    for marker, status in (
        ("token", "FAILED_TOKEN_BUDGET"),
        ("inspect", "FAILED_LAYOUT_INSPECT_BUDGET"),
        ("layout", "FAILED_LAYOUT_INSPECT_BUDGET"),
        ("patch", "FAILED_PATCH_BUDGET"),
        ("render", "FAILED_RENDER"),
        ("manim", "FAILED_RENDER"),
        ("reviewer", "FAILED_REVIEWER_SCHEMA"),
        ("subagent", "FAILED_REVIEWER_SCHEMA"),
    ):
        if marker in text:
            return status
    return "FAILED_NO_PATCH" if len(session.attempts) == 1 else "FAILED_EXTERNAL_ACCEPTANCE"
