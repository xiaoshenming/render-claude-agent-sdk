"""Partial evidence pack for interrupted Quality Agent runs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object

from .artifact_root import validate_existing_root
from .artifact_session import findings_payload, revisions_payload
from .artifact_transcripts import reviewer_messages, tool_results
from .artifact_usage import reviewer_tokens, token_ledger, usage_record
from .artifacts import (
    _agent_call,
    _write_json,
    _write_jsonl,
    _write_revisions,
    _write_text,
)
from .review_input_artifacts import write_review_input_artifacts
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
    validate_existing_root(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("input", "revisions", "evidence", "logs", "output"):
        (target / name).mkdir(exist_ok=True)
    write_review_input_artifacts(target, session)
    _write_revisions(target, session)
    _write_json(
        target / "evidence" / "layout.R0.baseline.json",
        thaw_json_object(baseline_layout_report),
    )
    _write_json(target / "evidence" / "findings.json", findings_payload(session))
    _write_json(target / "evidence" / "revisions.json", revisions_payload(session))
    _write_json(target / "logs" / "agent_call.partial.json", _agent_call(record))
    _write_jsonl(
        target / "logs" / "tool_calls.jsonl",
        [_tool_call(item) for item in record.tool_calls],
    )
    _write_transcript_logs(target, error)
    _write_json(
        target / "logs" / "subagent-results.json",
        {
            "results": [
                thaw_json_object(item)
                for item in getattr(error, "subagent_results", ())
            ]
        },
    )
    _write_json(
        target / "logs" / "token-ledger.json",
        token_ledger(
            record,
            getattr(error, "sdk_messages", ()),
            getattr(error, "subagent_results", ()),
        ),
    )
    failure = _failure(record, session, error)
    _write_json(target / "logs" / "failure.json", failure)
    _write_json(target / "output" / "decision.json", {"decision": "FAILED", **failure})
    current = session.current_revision
    _write_text(
        target / "output" / f"last_candidate.{current.revision_id}.py",
        current.code,
    )
    evidence = session.best_validated_evidence()
    if evidence is not None:
        revision_id = str(evidence["revision_id"])
        _write_text(
            target / "output" / f"best_render_passed.{revision_id}.py",
            session.get_revision(revision_id).code,
        )


def _write_transcript_logs(target: Path, error: Exception) -> None:
    sdk_messages = [
        thaw_json_object(item) for item in getattr(error, "sdk_messages", ())
    ]
    logs = target / "logs"
    _write_jsonl(logs / "parent-sdk-messages.jsonl", sdk_messages)
    _write_jsonl(
        logs / "reviewer-sdk-messages.jsonl",
        reviewer_messages(sdk_messages),
    )
    _write_jsonl(logs / "tool-results.jsonl", tool_results(sdk_messages))


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
        "call_id": item.call_id,
        "started_at_ms": item.started_at_ms,
        "finished_at_ms": item.finished_at_ms,
        "duration_ms": item.duration_ms,
    }


def _failure(record, session: QualitySession, error: Exception) -> dict[str, object]:
    reviewers = reviewer_tokens(getattr(error, "subagent_results", ()))
    known_total = (
        record.usage.total_tokens
        if record.usage_complete
        else max(record.usage.total_tokens, reviewers)
    )
    return {
        "status": _failure_status(record.error or str(error), session),
        "error_type": type(error).__name__,
        "error": str(error),
        "last_revision_id": session.current_revision.revision_id,
        "last_revision_code_hash": session.current_revision.code_hash,
        "best_render_passed": session.best_validated_evidence(),
        "tokens": usage_record(record.usage),
        "tokens_scope": "agent_tree",
        "reviewer_tokens": reviewers,
        "reviewer_tokens_included": record.usage_complete,
        "total_tokens_with_reviewers": known_total,
        "usage_complete": record.usage_complete,
        "token_limit_observations": list(record.token_limit_observations),
        "external_tool_ms": record.external_tool_ms,
        "turns": record.turns,
        "tool_calls": len(record.tool_calls),
    }


def _failure_status(error: str, session: QualitySession) -> str:
    # Submitted sessions are always recovered upstream, so no branch for
    # them exists here by design.
    text = error.lower()
    for marker, status in (
        ("timed out", "FAILED_TIMEOUT"),
        ("timeout", "FAILED_TIMEOUT"),
        ("elapsed time exceeds", "FAILED_TIMEOUT"),
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
    return (
        "FAILED_NO_PATCH"
        if len(session.attempts) == 1
        else "FAILED_EXTERNAL_ACCEPTANCE"
    )
