"""Persist shadow Agent calls and normalize per-case metrics."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from manim_quality.agents import AgentCallRecord, UsageSink
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.logic.eval_manifest import FrozenEvalCase
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    LogicDecision,
    LogicIssue,
)
from manim_quality.logic.shadow import ShadowCaseResult


class JsonUsageSink(UsageSink):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.record: AgentCallRecord | None = None

    def save(self, record: AgentCallRecord) -> None:
        self.record = record
        write_json(self.path, _call_record_dict(record))


class JsonSequenceUsageSink(UsageSink):
    def __init__(self, directory: Path, role: str) -> None:
        self.directory = directory
        self.role = role
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)
        name = f"{self.role}-call-{len(self.records):03d}.json"
        write_json(self.directory / name, _call_record_dict(record))


def case_result(
    case: FrozenEvalCase,
    record: AgentCallRecord,
    decision: LogicDecision,
    issues: Sequence[LogicIssue],
) -> ShadowCaseResult:
    usage = record.usage
    return ShadowCaseResult(
        sample_id=case.sample_id,
        truth=case.truth,
        decision=decision,
        issue_count=len(issues),
        issue_types=tuple(issue.issue_type for issue in issues),
        expected_issue_type=case.expected_issue_type,
        target_error_hit=_hits_target_lines(
            tuple(citation for issue in issues for citation in issue.evidence),
            case.target_lines,
        ),
        output_corrections=_output_corrections(record),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        turns=record.turns,
        observed_model_rounds=record.observed_model_rounds,
        elapsed_ms=record.elapsed_ms,
        error=None,
    )


def failed_result(
    case: FrozenEvalCase, record: AgentCallRecord | None, error: str
) -> ShadowCaseResult:
    usage = record.usage if record else None
    return ShadowCaseResult(
        sample_id=case.sample_id,
        truth=case.truth,
        decision=None,
        issue_count=0,
        issue_types=(),
        expected_issue_type=case.expected_issue_type,
        target_error_hit=(False if case.truth.value == "known_bad" else None),
        output_corrections=_output_corrections(record) if record else 0,
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0,
        cache_read_tokens=usage.cache_read_tokens if usage else 0,
        cache_write_tokens=usage.cache_write_tokens if usage else 0,
        turns=record.turns if record else 0,
        observed_model_rounds=record.observed_model_rounds if record else 0,
        elapsed_ms=record.elapsed_ms if record else 0,
        error=error,
    )


def _hits_target_lines(
    citations: Sequence[EvidenceCitation], target_lines: Sequence[int]
) -> bool:
    return any(
        citation.artifact is CitationArtifact.CANDIDATE_CODE
        and citation.line_start is not None
        and citation.line_end is not None
        and any(
            citation.line_start <= line <= citation.line_end for line in target_lines
        )
        for citation in citations
    )


def _output_corrections(record: AgentCallRecord) -> int:
    return sum(call.name == "StructuredOutputCorrection" for call in record.tool_calls)


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _call_record_dict(record: AgentCallRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "role": record.role,
        "model": record.model,
        "prompt": record.prompt,
        "prompt_version": record.prompt_version,
        "schema_version": record.schema_version,
        "tool_version": record.tool_version,
        "structured_output": (
            thaw_json_object(record.structured_output)
            if record.structured_output
            else None
        ),
        "tool_calls": [
            {
                "name": call.name,
                "input": thaw_json_object(call.input),
                "allowed": call.allowed,
                "error": call.error,
                "result_status": call.result_status,
                "result_hash": call.result_hash,
            }
            for call in record.tool_calls
        ],
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_read_tokens": record.usage.cache_read_tokens,
            "cache_write_tokens": record.usage.cache_write_tokens,
        },
        "turns": record.turns,
        "observed_model_rounds": record.observed_model_rounds,
        "elapsed_ms": record.elapsed_ms,
        "error": record.error,
    }
