"""Read-only directed verification for unresolved repair predicates."""

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents._runtime_models import (
    AgentRunFailed,
    CorrectableOutputError,
)
from manim_quality.agents.profile import AgentProfile, AgentRole
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.agents.usage import AgentCallRecord
from manim_quality.revisions.fingerprint import code_hash

from ._verifier_evidence import bind_candidate_evidence
from .diff_guard import DiffGuardResult
from .repair_plan import RepairPlan
from .validators.registry import ValidationReport, ValidationStatus
from .verifier_output_schema import VERIFIER_OUTPUT_SCHEMA

_PROMPT_PATH = Path(__file__).with_name("prompts") / "verifier.md"


class DirectedVerifierError(RuntimeError):
    def __init__(self, message: str, *, call_record: AgentCallRecord | None = None):
        self.call_record = call_record
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DirectedVerifierResult:
    verified: bool
    decision: str
    resolved_issue_ids: tuple[str, ...]
    review_gaps: tuple[str, ...]
    call_record: AgentCallRecord


class DirectedVerifier:
    def __init__(self, runtime: AgentRuntime, profile: AgentProfile) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be AgentRuntime")
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        if profile.role is not AgentRole.VERIFIER:
            raise ValueError(
                "Directed Verifier requires the read-only verifier profile"
            )
        self._runtime = runtime
        self._profile = profile

    def verify(
        self,
        *,
        run_id: str,
        plan: RepairPlan,
        diff: DiffGuardResult,
        validation: ValidationReport,
        before_code: str,
        workspace: Path,
        candidate_path: Path,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int = 0,
        reserved_cache_write_tokens: int = 0,
    ) -> DirectedVerifierResult:
        if not diff.passed or not validation.requires_directed_verifier:
            raise DirectedVerifierError("directed verification is not required")
        if code_hash(before_code) != plan.source_code_hash:
            raise DirectedVerifierError("before_code does not match repair plan")
        candidate = _candidate_path(workspace, candidate_path)
        patched = candidate.read_text(encoding="utf-8")
        unresolved = _unresolved_issue_ids(validation)
        validator = _output_validator(before_code, patched, plan, unresolved)
        prompt = _prompt(before_code, patched, plan, validation)
        request = AgentRunRequest(
            run_id=run_id,
            profile=self._profile,
            prompt=prompt,
            output_schema=VERIFIER_OUTPUT_SCHEMA,
            workspace=workspace,
            readable_paths=(candidate,),
            editable_paths=(),
            context_bytes=_context_bytes(prompt),
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=reserved_cache_read_tokens,
            reserved_cache_write_tokens=reserved_cache_write_tokens,
            output_validator=validator,
        )
        try:
            result = self._runtime.run(request)
            bound = _bind_output(
                result.structured_output, before_code, patched, plan, unresolved
            )
        except AgentRunFailed as error:
            cause = error.__cause__
            message = str(cause) if cause is not None else str(error)
            raise DirectedVerifierError(message, call_record=error.record) from error
        return DirectedVerifierResult(
            verified=bound["decision"] == "verified",
            decision=bound["decision"],
            resolved_issue_ids=tuple(
                item["issue_id"] for item in bound["results"] if item["resolved"]
            ),
            review_gaps=tuple(bound["review_gaps"]),
            call_record=result.record,
        )


def _output_validator(
    before: str, code: str, plan: RepairPlan, issue_ids: tuple[str, ...]
):
    def validate(value: Mapping[str, object]) -> None:
        try:
            _bind_output(value, before, code, plan, issue_ids)
        except (TypeError, ValueError) as error:
            raise CorrectableOutputError(str(error)) from error

    return validate


def _bind_output(
    value: Mapping[str, object],
    before: str,
    code: str,
    plan: RepairPlan,
    issue_ids: tuple[str, ...],
) -> dict[str, object]:
    if set(value) != {"decision", "results", "review_gaps"}:
        raise ValueError("verifier output fields do not match schema")
    decision = value.get("decision")
    if decision not in {"verified", "rejected", "human_review"}:
        raise ValueError("verifier decision is invalid")
    results = _result_items(value.get("results"), before, code, plan)
    if tuple(item["issue_id"] for item in results) != issue_ids:
        raise ValueError("verifier results must match unresolved issue order")
    gaps = _string_list(value.get("review_gaps"), "review_gaps")
    resolved = [item["resolved"] for item in results]
    if decision == "verified" and (not all(resolved) or gaps):
        raise ValueError("verified requires all issues resolved and no gaps")
    if decision == "rejected" and (all(resolved) or gaps):
        raise ValueError("rejected requires an unresolved issue and no gaps")
    if decision == "human_review" and not gaps:
        raise ValueError("human_review requires review gaps")
    return {"decision": decision, "results": results, "review_gaps": gaps}


def _result_items(
    value: object, before: str, code: str, plan: RepairPlan
) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("verifier results must be an array")
    return [_result_item(item, before, code, plan) for item in value]


def _result_item(
    value: object, before: str, code: str, plan: RepairPlan
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "issue_id",
        "resolved",
        "candidate_evidence",
        "reason",
    }:
        raise ValueError("verifier result fields do not match schema")
    issue_id = _text(value.get("issue_id"), "issue_id")
    resolved = value.get("resolved")
    if type(resolved) is not bool:
        raise TypeError("resolved must be bool")
    _text(value.get("reason"), "reason")
    bind_candidate_evidence(
        value.get("candidate_evidence"),
        before,
        code,
        plan,
        issue_id,
        require_changed=resolved,
    )
    return {"issue_id": issue_id, "resolved": resolved}


def _unresolved_issue_ids(validation: ValidationReport) -> tuple[str, ...]:
    values: list[str] = []
    for check in validation.checks:
        if check.status is ValidationStatus.UNRESOLVED and check.issue_id:
            if check.issue_id not in values:
                values.append(check.issue_id)
    if not values:
        raise DirectedVerifierError("unresolved validation has no bound issue")
    return tuple(values)


def _prompt(
    before: str, after: str, plan: RepairPlan, validation: ValidationReport
) -> str:
    payload = {
        "plan_id": plan.plan_id,
        "target_scene_ids": list(plan.target_scene_ids),
        "issues": [
            {
                "issue_id": issue.issue_id,
                "expected": issue.expected,
                "observed": issue.observed,
                "target_scene_ids": list(issue.target_scene_ids),
            }
            for issue in plan.issues
        ],
        "unresolved": [
            {"issue_id": check.issue_id, "detail": check.detail}
            for check in validation.checks
            if check.status is ValidationStatus.UNRESOLVED
        ],
        "diff": _diff(before, after),
    }
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return template.replace("{{VERIFICATION_INPUT_JSON}}", encoded)


def _candidate_path(workspace: Path, candidate_path: Path) -> Path:
    root = Path(workspace).resolve(strict=True)
    candidate = Path(candidate_path).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise DirectedVerifierError("candidate_path must be inside workspace")
    return candidate


def _context_bytes(prompt: str) -> int:
    schema = json.dumps(VERIFIER_OUTPUT_SCHEMA, sort_keys=True, separators=(",", ":"))
    return len(prompt.encode("utf-8")) + len(schema.encode("utf-8"))


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be an array")
    return [_text(item, f"{name} item") for item in value]


def _diff(before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="before.py",
            tofile="after.py",
        )
    )
