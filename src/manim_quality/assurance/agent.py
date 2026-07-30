from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from manim_quality.agents.profile import assurance_profile
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.operator.reviewers import run_reviewers

from .contracts import ASSURANCE_OUTPUT_SCHEMA
from .models import AssuranceCase
from .toolset import AssuranceToolset
from .verification import AssuranceVerification, VerificationConfig

PROMPT = Path(__file__).with_name("prompt.md")


@dataclass(frozen=True, slots=True)
class FinalAssuranceResult:
    output: dict[str, object]
    reports: dict[str, object]
    reviewers: tuple[dict[str, object], ...]
    call_record: object


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
            prompt_version="final-assurance-v2",
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
        prompt = PROMPT.read_text(encoding="utf-8") + (
            f"\n\ncase_key: {case.key}\n题目：{case.question}\n"
        )
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
        result = self.runtime.run(request)
        _validate_reviewers(reviewers)
        return FinalAssuranceResult(
            output=thaw_json_object(result.structured_output),
            reports={name: report.as_dict() for name, report in tools.reports.items()},
            reviewers=reviewers,
            call_record=_merge_reviewer_records(result.record, reviewer_records),
        )


def _native_reviewers(runtime, model, case, verification):
    if verification is None or case.source_path is None:
        return (), ()
    return run_reviewers(
        runtime,
        candidate_path=case.source_path,
        model=model,
        effort="low",
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
    expected = {"math_geometry_reviewer", "animation_lifecycle_reviewer"}
    observed = {
        str(item.get("agent_type"))
        for item in reviewers
        if item.get("is_error") is False and isinstance(item.get("payload"), dict)
    }
    if observed != expected or len(reviewers) != len(expected):
        raise RuntimeError(
            "final assurance requires exactly two completed specialist reviewers"
        )
