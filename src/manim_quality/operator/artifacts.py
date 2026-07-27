"""Deterministic artifact pack for one Quality Operator run."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object

from .agent import QualityOperatorResult
from .artifact_session import findings_payload, revisions_payload
from .artifact_usage import reviewer_tokens, usage_record
from .gate import GateDecision, GateResult
from .session import QualitySession

_OWNED_RUNTIME_DIRECTORIES = {"agent_runtime", "acceptance_runtime"}


def write_run_artifacts(
    *,
    root: Path,
    session: QualitySession,
    operator_result: QualityOperatorResult,
    gate_result: GateResult,
    baseline_layout_report: Mapping[str, object] | None = None,
) -> None:
    target = Path(root)
    _validate_existing_root(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("input", "revisions", "evidence", "logs", "output"):
        (target / name).mkdir()
    _write_inputs(target, session)
    _write_revisions(target, session)
    _write_evidence(target, session, gate_result, baseline_layout_report or {})
    _write_logs(target, session, operator_result, gate_result)
    _write_output(target, session, gate_result)


def _validate_existing_root(target: Path) -> None:
    if not target.exists():
        return
    unknown = {
        item.name
        for item in target.iterdir()
        if item.name not in _OWNED_RUNTIME_DIRECTORIES or not item.is_dir()
    }
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"artifact root has unknown existing content: {names}")


def _write_inputs(target: Path, session: QualitySession) -> None:
    _write_text(target / "input" / "problem.snapshot", session.problem_text)
    _write_text(target / "input" / "candidate.R0.py", session.baseline.code)


def _write_revisions(target: Path, session: QualitySession) -> None:
    for revision in session.attempts:
        scope = "baseline" if revision.scope is None else revision.scope.value
        _write_text(
            target / "revisions" / f"{revision.revision_id}.{scope}.py",
            revision.code,
        )


def _write_evidence(
    target: Path,
    session: QualitySession,
    gate_result: GateResult,
    baseline_layout_report: Mapping[str, object],
) -> None:
    _write_json(
        target / "evidence" / "layout.R0.baseline.json",
        thaw_json_object(baseline_layout_report),
    )
    _write_json(target / "evidence" / "findings.json", findings_payload(session))
    _write_json(target / "evidence" / "revisions.json", revisions_payload(session))
    revision_id = session.submitted_revision_id or session.current_revision.revision_id
    if gate_result.validation is not None:
        _write_json(
            target / "evidence" / f"validation.{revision_id}.json",
            _validation(gate_result.validation),
        )
    if gate_result.layout_report is not None:
        _write_json(
            target / "evidence" / f"layout.{revision_id}.json",
            thaw_json_object(gate_result.layout_report),
        )


def _write_logs(
    target: Path,
    session: QualitySession,
    operator_result: QualityOperatorResult,
    gate_result: GateResult,
) -> None:
    record = operator_result.call_record
    _write_json(target / "logs" / "agent_call.json", _agent_call(record))
    _write_jsonl(
        target / "logs" / "tool_calls.jsonl",
        [
            {
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
            for item in record.tool_calls
        ],
    )
    _write_jsonl(
        target / "logs" / "parent-sdk-messages.jsonl",
        [thaw_json_object(item) for item in operator_result.sdk_messages],
    )
    _write_json(
        target / "logs" / "subagent-results.json",
        {
            "results": [
                thaw_json_object(item) for item in operator_result.subagent_results
            ]
        },
    )
    decision = _decision(session, operator_result, gate_result)
    _write_json(target / "logs" / "run_summary.json", decision)
    _write_json(target / "output" / "decision.json", decision)


def _write_output(target: Path, session, gate_result: GateResult) -> None:
    if gate_result.decision is GateDecision.PROPOSED:
        assert gate_result.final_revision is not None
        _write_text(
            target / "output" / "proposed_candidate.py",
            gate_result.final_revision.code,
        )
        return
    assert gate_result.rollback_revision is not None
    rollback = gate_result.rollback_revision
    _write_text(
        target / "output" / f"rollback.{rollback.revision_id}.py",
        rollback.code,
    )
    evidence = session.best_validated_evidence()
    if evidence is not None:
        revision_id = str(evidence["revision_id"])
        _write_text(
            target / "output" / f"best_render_passed.{revision_id}.py",
            session.get_revision(revision_id).code,
        )


def _agent_call(record) -> dict[str, object]:
    usage = record.usage
    return {
        "run_id": record.run_id,
        "role": record.role,
        "model": record.model,
        "prompt": record.prompt,
        "prompt_version": record.prompt_version,
        "schema_version": record.schema_version,
        "tool_version": record.tool_version,
        "structured_output": (
            None
            if record.structured_output is None
            else thaw_json_object(record.structured_output)
        ),
        "usage": usage_record(usage),
        "turns": record.turns,
        "observed_model_rounds": record.observed_model_rounds,
        "elapsed_ms": record.elapsed_ms,
        "external_tool_ms": record.external_tool_ms,
        "usage_complete": record.usage_complete,
        "error": record.error,
    }


def _decision(
    session: QualitySession,
    operator_result: QualityOperatorResult,
    gate_result: GateResult,
) -> dict[str, object]:
    record = operator_result.call_record
    final, rollback = gate_result.final_revision, gate_result.rollback_revision
    held = operator_result.agent_held
    reviewer_total = reviewer_tokens(operator_result.subagent_results)
    return {
        "decision": gate_result.decision.value,
        "agent_held": held,
        "hold_reason": operator_result.hold_reason,
        "submitted_revision_id": (
            None if held else operator_result.revision.revision_id
        ),
        "last_revision_id": operator_result.revision.revision_id,
        "final_revision_id": None if final is None else final.revision_id,
        "rollback_revision_id": None if rollback is None else rollback.revision_id,
        "best_render_passed": session.best_validated_evidence(),
        "reasons": list(gate_result.reasons),
        "agent_summary": operator_result.summary,
        "turns": record.turns,
        "tool_calls": len(record.tool_calls),
        "elapsed_ms": record.elapsed_ms,
        "external_tool_ms": record.external_tool_ms,
        "tokens": usage_record(record.usage),
        "reviewer_tokens": reviewer_total,
        "total_tokens_with_reviewers": (
            record.usage.total_tokens + reviewer_total
        ),
        "layout_report": gate_result.layout_report,
        "validation": _validation(gate_result.validation),
    }


def _validation(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "passed": value.passed,
        "improved": value.improved,
        "summary": value.summary,
        "details": thaw_json_object(value.details),
        "fingerprint": value.fingerprint,
        "revision_id": value.revision_id,
        "code_hash": value.code_hash,
        "problem_hash": value.problem_hash,
    }


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _write_jsonl(path: Path, values: list[object]) -> None:
    lines = [
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for value in values
    ]
    _write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def _write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
