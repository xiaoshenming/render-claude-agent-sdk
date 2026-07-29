from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents.profile import assurance_profile
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.contracts._json_values import thaw_json_object

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
            prompt_version="final-assurance-practical-v3.1",
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
            subagents=verification.reviewers if verification is not None else (),
            effort="low",
        )
        result = self.runtime.run(request)
        reviewers = tuple(
            thaw_json_object(item) for item in result.subagent_results
        )
        _validate_reviewers(reviewers)
        reports = {
            name: report.as_dict() for name, report in tools.reports.items()
        }
        output = thaw_json_object(result.structured_output)
        _normalize_derived_parameter_issues(output, reports, case.key)
        _normalize_confirmed_anchor_drift(output)
        return FinalAssuranceResult(
            output=output,
            reports=reports,
            reviewers=reviewers,
            call_record=result.record,
        )


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


def _normalize_derived_parameter_issues(
    output: dict[str, object],
    reports: dict[str, object],
    case_key: str,
) -> None:
    code_review = reports.get("inspect_code_review")
    if not isinstance(code_review, dict):
        return
    evidence = code_review.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return
    source = evidence[0] if isinstance(evidence[0], dict) else {}
    mismatches = source.get("derived_parameter_mismatches")
    if not isinstance(mismatches, list) or not mismatches:
        return
    issues = output.get("issues")
    if not isinstance(issues, list):
        return
    existing = " ".join(
        str(item.get("summary", ""))
        for item in issues
        if isinstance(item, dict)
    )
    evidence_ids = [f"{case_key}:final-source"]
    risk_frames = reports.get("inspect_risk_frames")
    if isinstance(risk_frames, dict) and risk_frames.get("evidence"):
        evidence_ids.append(f"{case_key}:risk-frames")
    for mismatch in mismatches:
        if not isinstance(mismatch, dict):
            continue
        expected, actual = mismatch.get("expected"), mismatch.get("actual")
        if str(expected) in existing and str(actual) in existing:
            continue
        issues.append(
            {
                "severity": "high",
                "category": "function_visualization",
                "summary": (
                    f"函数图像派生系数错误：{mismatch.get('helper')} 第"
                    f"{mismatch.get('line')}行将 {mismatch.get('parameter')} "
                    f"设为 {actual}，但按 {mismatch.get('expression')} "
                    f"复算应为 {expected}。这会使所绘函数斜率与同组选项参数"
                    "不一致，不能按几何示意图未严格按比例降级。"
                ),
                "evidence_ids": evidence_ids,
            }
        )
    if output.get("status") != "incomplete":
        output["status"] = "review"


def _normalize_confirmed_anchor_drift(output: dict[str, object]) -> None:
    issues = output.get("issues")
    if not isinstance(issues, list):
        return
    drift_terms = ("漂移", "脱离", "悬空", "旧坐标", "缩放前", "适配前")
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        summary = str(issue.get("summary", ""))
        evidence_ids = issue.get("evidence_ids")
        has_video = (
            isinstance(evidence_ids, list)
            and any(str(item).endswith(":risk-frames") for item in evidence_ids)
        )
        if has_video and any(term in summary for term in drift_terms):
            issue["severity"] = "high"
