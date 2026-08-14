"""Single-session Claude SDK Quality Operator facade."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from manim_quality.agents._runtime_models import AgentRunFailed, CorrectableOutputError
from manim_quality.agents.profile import AgentProfile, AgentRole
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import AgentCallRecord

from .candidate_io import find_baseline_candidate
from .directed_feedback import directed_reviewer_context
from .models import CandidateAttempt
from .output_schema import OPERATOR_OUTPUT_SCHEMA
from .ports import LayoutInspector, RelationChecker, RevisionValidator
from .request_builder import operator_request
from .review_context import load_final_assurance_context
from .reviewers import run_reviewers
from .session import QualitySession
from .source_view import extract_solution

PROMPT_PATH = Path(__file__).with_name("prompts") / "quality_operator_v3.md"


@dataclass(frozen=True, slots=True)
class QualityOperatorResult:
    revision: CandidateAttempt
    summary: str
    call_record: AgentCallRecord
    sdk_messages: tuple[Mapping[str, object], ...] = ()
    subagent_results: tuple[Mapping[str, object], ...] = ()
    agent_held: bool = False
    hold_reason: str | None = None


class QualityOperatorAgent:
    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        profile: AgentProfile,
    ) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be AgentRuntime")
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        if profile.role is not AgentRole.OPERATOR:
            raise ValueError("Quality Operator requires the operator profile")
        self._runtime = runtime
        self._profile = profile

    def run(
        self,
        *,
        run_id: str,
        workspace: Path,
        session: QualitySession,
        relation_checker: RelationChecker,
        layout_inspector: LayoutInspector,
        revision_validator: RevisionValidator,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int = 0,
        reserved_cache_write_tokens: int = 0,
    ) -> QualityOperatorResult:
        if not isinstance(session, QualitySession):
            raise TypeError("session must be QualitySession")
        candidate_path, prompt, reviewer_results, reviewer_records = _review_context(
            self._runtime,
            self._profile.model,
            workspace,
            session,
        )
        request = operator_request(
            run_id=run_id,
            profile=self._profile,
            prompt=prompt,
            workspace=workspace,
            candidate_path=candidate_path,
            session=session,
            relation_checker=relation_checker,
            layout_inspector=layout_inspector,
            revision_validator=revision_validator,
            context_bytes=_context_bytes(prompt),
            output_validator=_output_validator(session),
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=reserved_cache_read_tokens,
            reserved_cache_write_tokens=reserved_cache_write_tokens,
        )
        try:
            result = self._runtime.run(request)
        except AgentRunFailed as error:
            recovered = _recover_submitted_output(session, error)
            if recovered is None:
                raise
            return recovered
        return _terminal_result(
            session,
            result,
            reviewer_results=reviewer_results,
            reviewer_records=reviewer_records,
        )


def _review_context(runtime, model, workspace, session):
    candidate_path = find_baseline_candidate(workspace, session.baseline.code)
    solution = extract_solution(candidate_path.read_text(encoding="utf-8"))
    line_count = solution.end_line - solution.start_line + 1
    reviewer_results = directed_reviewer_context(session.repair_feedback)
    reviewer_records = ()
    if reviewer_results is None:
        reviewer_results, reviewer_records = run_reviewers(
            runtime,
            candidate_path=candidate_path,
            problem_text=session.problem_text,
            solution_steps=session.solution_steps,
            model=model,
            effort="low",
        )
    reviewer_json = json.dumps(
        reviewer_results, ensure_ascii=False, separators=(",", ":")
    )
    assurance_json = json.dumps(
        load_final_assurance_context(workspace),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    prompt = (
        PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{CANDIDATE_PATH}}", str(candidate_path))
        .replace("{{REVIEWER_RESULTS}}", reviewer_json)
        .replace("{{PROBLEM_TEXT}}", session.problem_text)
        .replace("{{SOLUTION_STEPS}}", session.solution_steps)
        .replace(
            "{{REPAIR_FEEDBACK}}",
            json.dumps(
                session.repair_feedback,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        .replace("{{FINAL_ASSURANCE_ISSUES}}", assurance_json)
        .replace("{{SOLUTION_START_LINE}}", str(solution.start_line))
        .replace("{{SOLUTION_END_LINE}}", str(solution.end_line))
        .replace("{{SOLUTION_LINE_COUNT}}", str(line_count))
    )
    return candidate_path, prompt, reviewer_results, reviewer_records


def _terminal_result(
    session: QualitySession,
    result,
    *,
    reviewer_results=(),
    reviewer_records=(),
) -> QualityOperatorResult:
    summary = _bind_output(result.structured_output, session)
    held = result.structured_output.get("status") == "held"
    reason = result.structured_output.get("hold_reason")
    record = result.record
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
    return QualityOperatorResult(
        revision=session.current_revision,
        summary=summary,
        call_record=record,
        sdk_messages=tuple(result.sdk_messages),
        subagent_results=tuple(reviewer_results),
        agent_held=held,
        hold_reason=str(reason) if held and reason is not None else None,
    )


def _recover_submitted_output(
    session: QualitySession,
    error: AgentRunFailed,
) -> QualityOperatorResult | None:
    """A submitted revision survives any later session failure.

    submit_revision already required a passing validation, a fresh layout
    inspection, and zero blocking issues; the outer gate re-renders and
    re-inspects independently, so no terminal summary can add evidence.
    """

    submitted = session.submitted_revision_id
    if submitted is None:
        return None
    revision = session.get_revision(submitted)
    reason = (error.record.error or "unknown error")[:200]
    return QualityOperatorResult(
        revision=revision,
        summary=(
            "宿主从 submit_revision 的权威会话状态恢复终态摘要"
            f"（提交后错误：{reason}）；候选仍需通过外层独立渲染与布局复检。"
        ),
        call_record=error.record,
        sdk_messages=tuple(error.sdk_messages),
        subagent_results=tuple(error.subagent_results),
    )


def _output_validator(session: QualitySession):
    def validate(value: Mapping[str, object]) -> None:
        try:
            _bind_output(value, session)
        except (TypeError, ValueError) as error:
            raise CorrectableOutputError(str(error)) from error

    return validate


def _bind_output(
    value: Mapping[str, object],
    session: QualitySession,
) -> str:
    status = value.get("status")
    if status == "submitted":
        return _bind_submitted_output(value, session)
    if status == "held":
        return _bind_held_output(value, session)
    raise ValueError("invalid Quality Operator terminal output")


def _bind_submitted_output(
    value: Mapping[str, object],
    session: QualitySession,
) -> str:
    required = {
        "status",
        "submitted_revision_id",
        "code_hash",
        "problem_hash",
        "summary",
    }
    if set(value) != required:
        raise ValueError("invalid Quality Operator terminal output")
    submitted = session.submitted_revision_id
    if submitted is None:
        raise ValueError("submit_revision tool must run before terminal output")
    revision = session.get_revision(submitted)
    expected = (submitted, revision.code_hash, session.problem_hash)
    actual = (
        value.get("submitted_revision_id"),
        value.get("code_hash"),
        value.get("problem_hash"),
    )
    if actual != expected:
        raise ValueError("terminal output does not bind submitted revision")
    return _bounded_summary(value)


def _bind_held_output(
    value: Mapping[str, object],
    session: QualitySession,
) -> str:
    if not set(value) <= {"status", "summary", "hold_reason"}:
        raise ValueError("held output allows only status, summary, hold_reason")
    if session.submitted_revision_id is not None:
        raise ValueError("held output is forbidden after a real submission")
    reason = value.get("hold_reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValueError("hold_reason must be a bounded non-empty string")
    return _bounded_summary(value)


def _bounded_summary(value: Mapping[str, object]) -> str:
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 2_000:
        raise ValueError("summary must be a bounded non-empty string")
    return summary


def _context_bytes(prompt: str) -> int:
    schema = json.dumps(
        OPERATOR_OUTPUT_SCHEMA,
        sort_keys=True,
        separators=(",", ":"),
    )
    return len(prompt.encode("utf-8")) + len(schema.encode("utf-8"))
