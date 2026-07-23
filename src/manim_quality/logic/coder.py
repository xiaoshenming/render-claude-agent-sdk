"""Scene-scoped Logic Coder over the shared Claude Agent SDK runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents._runtime_models import AgentRunFailed
from manim_quality.agents.profile import AgentProfile, AgentRole
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.agents.usage import AgentCallRecord
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.revisions.fingerprint import code_hash

from .coder_output_schema import CODER_OUTPUT_SCHEMA
from .diff_guard import DiffGuardResult, evaluate_logic_diff
from .repair_plan import RepairPlan
from .schemas import CitationArtifact
from .validators.registry import ValidationReport, validate_candidate

_PROMPT_PATH = Path(__file__).with_name("prompts") / "coder.md"


class LogicCoderError(RuntimeError):
    def __init__(self, message: str, *, call_record: AgentCallRecord | None = None):
        self.call_record = call_record
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LogicCoderResult:
    candidate_code: str
    diff: DiffGuardResult
    validation: ValidationReport
    call_record: AgentCallRecord


class LogicCoder:
    def __init__(self, runtime: AgentRuntime, profile: AgentProfile) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be AgentRuntime")
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        if profile.role is not AgentRole.CODER:
            raise ValueError("Logic Coder requires the Read+Edit coder profile")
        self._runtime = runtime
        self._profile = profile

    def patch(
        self,
        *,
        run_id: str,
        plan: RepairPlan,
        workspace: Path,
        candidate_path: Path,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int = 0,
        reserved_cache_write_tokens: int = 0,
        retry_context: Mapping[str, object] | None = None,
    ) -> LogicCoderResult:
        candidate = _candidate_path(workspace, candidate_path)
        before = _read_candidate(candidate)
        if code_hash(before) != plan.source_code_hash:
            raise LogicCoderError("candidate no longer matches repair plan")
        prompt = _prompt(plan, retry_context)
        request = AgentRunRequest(
            run_id=run_id,
            profile=self._profile,
            prompt=prompt,
            output_schema=CODER_OUTPUT_SCHEMA,
            workspace=workspace,
            readable_paths=(candidate,),
            editable_paths=(candidate,),
            context_bytes=_context_bytes(prompt),
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=reserved_cache_read_tokens,
            reserved_cache_write_tokens=reserved_cache_write_tokens,
            tool_policies={"Read": ToolInputPolicy(max_calls=50)},
        )
        try:
            call = self._runtime.run(request)
            after = _read_candidate(candidate)
            diff = evaluate_logic_diff(before, after, plan)
            validation = validate_candidate(before, after, plan, diff)
            reason = _rejection_reason(diff, validation)
            if reason is not None:
                raise LogicCoderError(reason, call_record=call.record)
        except AgentRunFailed as error:
            if _read_candidate(candidate) == before:
                _restore(candidate, before)
            raise LogicCoderError(str(error), call_record=error.record) from error
        except Exception:
            _restore(candidate, before)
            raise
        return LogicCoderResult(after, diff, validation, call.record)


def _candidate_path(workspace: Path, candidate_path: Path) -> Path:
    root = Path(workspace).resolve(strict=True)
    candidate = Path(candidate_path).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise LogicCoderError("candidate_path must be a file inside the workspace")
    return candidate


def _read_candidate(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise LogicCoderError("candidate.py must be readable UTF-8") from error


def _restore(path: Path, before: str) -> None:
    path.write_text(before, encoding="utf-8")


def _prompt(plan: RepairPlan, retry_context: Mapping[str, object] | None) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    payload = {
        "plan_id": plan.plan_id,
        "source_code_hash": plan.source_code_hash,
        "target_scenes": list(plan.target_scene_ids),
        "allowed_regions": [
            {
                "scene_id": region.scene_id,
                "line_start": region.line_start,
                "line_end": region.line_end,
            }
            for region in plan.allowed_edit_regions
        ],
        "issues": [_issue_payload(issue) for issue in plan.issues],
        "forbidden_changes": list(plan.forbidden_changes),
        "retry_context": dict(retry_context) if retry_context is not None else None,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return template.replace("{{REPAIR_PLAN_JSON}}", encoded)


def _issue_payload(issue) -> dict[str, object]:
    citations = [
        {
            "scene_id": citation.scene_id,
            "line_start": citation.line_start,
            "line_end": citation.line_end,
            "excerpt": citation.excerpt,
        }
        for citation in issue.evidence
        if citation.artifact is CitationArtifact.CANDIDATE_CODE
    ]
    return {
        "issue_id": issue.issue_id,
        "issue_type": issue.issue_type,
        "repair_scope": issue.repair_scope,
        "target_scene_ids": list(issue.target_scene_ids),
        "candidate_evidence": citations,
        "expected": issue.expected,
        "observed": issue.observed,
        "acceptance_predicates": [
            thaw_json_object(predicate) for predicate in issue.acceptance_predicates
        ],
        "non_goals": list(issue.non_goals),
    }


def _context_bytes(prompt: str) -> int:
    schema = json.dumps(CODER_OUTPUT_SCHEMA, sort_keys=True, separators=(",", ":"))
    return len(prompt.encode("utf-8")) + len(schema.encode("utf-8"))


def _rejection_reason(
    diff: DiffGuardResult, validation: ValidationReport
) -> str | None:
    if not diff.passed:
        return "; ".join(diff.violations)
    if not validation.passed and not validation.requires_directed_verifier:
        failed = [check.detail for check in validation.checks if check.status == "fail"]
        return "; ".join(failed) or "deterministic validation failed"
    return None
