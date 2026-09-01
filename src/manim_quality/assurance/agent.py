from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from manim_quality.agents._runtime_models import AgentRunFailed
from manim_quality.agents.profile import assurance_profile
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.agents.usage import AgentCallRecord
from manim_quality.operator.reviewers import run_reviewers

from .contracts import ASSURANCE_OUTPUT_SCHEMA
from .models import AssuranceCase
from .policy import (
    POLICY_SHA256,
    POLICY_VERSION,
    PolicyAdjustedAssessment,
    RawAgentAssessment,
    apply_assurance_policy,
)
from .toolset import AssuranceToolset
from .verification import AssuranceVerification, VerificationConfig

PROMPT = Path(__file__).with_name("prompt.md")


@dataclass(frozen=True, slots=True)
class FinalAssuranceResult:
    output: dict[str, object]
    reports: dict[str, object]
    reviewers: tuple[dict[str, object], ...]
    call_record: object
    parent_call_record: object
    parent_attempt_records: tuple[AgentCallRecord, ...]
    raw_assessment: RawAgentAssessment
    policy_assessment: PolicyAdjustedAssessment


class FinalAssuranceAgent:
    def __init__(
        self,
        runtime: AgentRuntime,
        model: str,
        verification_config: VerificationConfig | None = None,
    ) -> None:
        self.runtime = runtime
        self.profile = assurance_profile(
            model=model,
            prompt_version=f"final-assurance-practical-v3.1+{POLICY_VERSION}",
            schema_version="final-assurance-output-v2",
            tool_version="final-assurance-tools-v2",
        )
        self.verification_config = verification_config

    def run(
        self,
        case: AssuranceCase,
        output_dir: Path,
        *,
        estimated_input_tokens: int = 18_000,
        reserved_output_tokens: int = 4_000,
    ) -> FinalAssuranceResult:
        verification = (
            AssuranceVerification(case, output_dir, self.verification_config)
            if self.verification_config is not None
            else None
        )
        tools = AssuranceToolset(case, output_dir, verification)
        reviewers, reviewer_records = _native_reviewers(
            self.runtime, self.profile.model, case, verification
        )
        _validate_reviewers(reviewers)
        prompt = _assurance_prompt(case, reviewers)
        request = AgentRunRequest(
            run_id=f"assurance-{case.key}",
            profile=self.profile,
            prompt=prompt,
            output_schema=ASSURANCE_OUTPUT_SCHEMA,
            workspace=output_dir,
            readable_paths=(),
            editable_paths=(),
            context_bytes=len(prompt.encode()) + len(json.dumps(
                ASSURANCE_OUTPUT_SCHEMA).encode()),
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=40_000,
            reserved_cache_write_tokens=0,
            output_validator=tools.validate_output,
            managed_tools=tools.grants(),
            subagents=(),
            effort="low",
        )
        result, parent_attempts = _run_parent_with_protocol_retry(
            self.runtime, request, output_dir
        )
        reports = {
            name: report.as_dict() for name, report in tools.reports.items()
        }
        raw = RawAgentAssessment(tools.normalize_output(result.structured_output))
        adjusted = apply_assurance_policy(
            raw, reports, case.key, reviewers=reviewers)
        parent_record = _merge_parent_attempt_records(parent_attempts)
        return FinalAssuranceResult(
            output=adjusted.output,
            reports=reports,
            reviewers=reviewers,
            call_record=_merge_reviewer_records(parent_record, reviewer_records),
            parent_call_record=parent_record,
            parent_attempt_records=parent_attempts,
            raw_assessment=raw,
            policy_assessment=adjusted,
        )


_RETRYABLE_PARENT_PROTOCOL_ERRORS = (
    "sdk result has no structured output object",
    "structured output correction limit exceeded",
)


def _run_parent_with_protocol_retry(runtime, request, output_dir):
    """Retry only a malformed Final Assurance parent response once.

    Reviewers have already completed before this boundary.  The retry reuses
    the same immutable prompt, schema, workspace and read-only toolset; it does
    not re-enter Render or the Quality Coder.
    """
    attempts: list[AgentCallRecord] = []
    for attempt in (1, 2):
        current = request if attempt == 1 else replace(
            request, run_id=f"{request.run_id}-protocol-retry-1"
        )
        try:
            result = runtime.run(current)
        except AgentRunFailed as error:
            attempts.append(error.record)
            _record_parent_attempt(output_dir, attempt, error.record)
            if attempt == 1 and _is_retryable_parent_protocol_error(error.record):
                continue
            raise
        attempts.append(result.record)
        _record_parent_attempt(output_dir, attempt, result.record)
        return result, tuple(attempts)
    raise AssertionError("bounded Final Assurance retry exhausted")


def _is_retryable_parent_protocol_error(record: AgentCallRecord) -> bool:
    error = str(record.error or "").lower()
    return any(marker in error for marker in _RETRYABLE_PARENT_PROTOCOL_ERRORS)


def _record_parent_attempt(
    output_dir: Path, attempt: int, record: AgentCallRecord
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    usage = record.usage
    payload = {
        "attempt": attempt,
        "run_id": record.run_id,
        "status": "failed" if record.error else "succeeded",
        "error": record.error,
        "elapsed_ms": record.elapsed_ms,
        "turns": record.turns,
        "tool_calls": len(record.tool_calls),
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
        },
    }
    with (output_dir / "parent-attempts.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _merge_parent_attempt_records(
    attempts: tuple[AgentCallRecord, ...],
) -> AgentCallRecord:
    record = attempts[-1]
    for previous in attempts[:-1]:
        record = replace(
            record,
            usage=previous.usage.plus(record.usage),
            turns=previous.turns + record.turns,
            observed_model_rounds=(
                previous.observed_model_rounds + record.observed_model_rounds
            ),
            tool_calls=tuple(previous.tool_calls) + tuple(record.tool_calls),
            elapsed_ms=previous.elapsed_ms + record.elapsed_ms,
            external_tool_ms=previous.external_tool_ms + record.external_tool_ms,
            usage_complete=previous.usage_complete and record.usage_complete,
            token_limit_observations=(
                tuple(previous.token_limit_observations)
                + tuple(record.token_limit_observations)
            ),
        )
    return record


def _assurance_prompt(case, reviewers) -> str:
    return PROMPT.read_text(encoding="utf-8") + (
        f"\n\nassurance_policy: {POLICY_VERSION}@{POLICY_SHA256}\n"
        f"\n\ncase_key: {case.key}\n"
        "权威内容已按职责分别交给四个只读 Reviewer；Parent 只汇总回执，"
        "不得重新审题或重复制造输入问题。\n"
        "两路必需 Reviewer、视觉版式与可用时的题图保真 Reviewer 已由编排器处理，"
        "不要再调用 Agent 工具。以下回执是本次终审的只读证据：\n"
        f"{json.dumps(reviewers, ensure_ascii=False)}\n"
    )


def _native_reviewers(runtime, model, case, verification):
    # Formal reviewers inspect the immutable source and do not require a new
    # render. ``verification`` only enables the optional execution/layout
    # rerun tools used by the parent assurance agent.
    if case.source_path is None:
        return (), ()
    return run_reviewers(
        runtime,
        candidate_path=case.source_path,
        problem_text=case.question,
        solution_steps=case.solution_steps,
        final_answer=case.final_answer,
        parsed_standard_answer=(
            getattr(case, "parsed_standard_answer", "")
            or case.final_answer),
        teaching_script=case.solution_steps,
        reviewer_supplemental_notes=(
            getattr(case, "reviewer_supplemental_notes", None) or {}),
        model=model,
        effort="medium",
    )


def _merge_reviewer_records(record, reviewer_records):
    for reviewer in reviewer_records:
        record = replace(
            record,
            usage=record.usage.plus(reviewer.usage),
            turns=record.turns + reviewer.turns,
            observed_model_rounds=(
                record.observed_model_rounds + reviewer.observed_model_rounds
            ),
            tool_calls=tuple(reviewer.tool_calls) + tuple(record.tool_calls),
            elapsed_ms=record.elapsed_ms + reviewer.elapsed_ms,
        )
    return record


def _validate_reviewers(reviewers: tuple[dict[str, object], ...]) -> None:
    required = {
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
    }
    completed = {
        str(item.get("agent_type"))
        for item in reviewers
        if item.get("is_error") is False and isinstance(item.get("payload"), dict)
    }
    observed = [str(item.get("agent_type")) for item in reviewers]
    allowed = required | {"visual_layout_reviewer", "figure_fidelity_reviewer"}
    if (
        not required.issubset(completed)
        or not set(observed).issubset(allowed)
        or len(observed) != len(set(observed))
    ):
        raise RuntimeError(
            "final assurance requires both core specialist reviewers"
        )
