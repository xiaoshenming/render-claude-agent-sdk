"""Registry of deterministic post-patch logic checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from tools.logic_engine_mvp.logic_engine_mvp.logic_facts import (
    extract_deterministic_logic_facts,
)

from manim_quality.contracts._validation import require_non_empty_string

from .._scene_evidence import extract_scenes
from ..diff_guard import DiffGuardResult
from ..repair_plan import RepairPlan
from .geometry_resolution import targeted_geometry_results
from .predicate_evidence import predicate_has_bound_evidence
from .scene_risk import new_scene_risks

_PRESENT_KINDS = frozenset(
    {
        "text_present",
        "must_contain",
        "expected_answer_present",
        "formula_present",
        "coordinate_present",
    }
)
_ABSENT_KINDS = frozenset({"text_absent", "must_not_contain"})


class ValidationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    validator: str
    status: ValidationStatus
    detail: str
    issue_id: str | None = None

    def __post_init__(self) -> None:
        require_non_empty_string(self.validator, "validator")
        if not isinstance(self.status, ValidationStatus):
            raise TypeError("status must be ValidationStatus")
        require_non_empty_string(self.detail, "detail")
        if self.issue_id is not None:
            require_non_empty_string(self.issue_id, "issue_id")


@dataclass(frozen=True, slots=True)
class ValidationReport:
    checks: tuple[ValidationCheck, ...]
    passed: bool
    requires_directed_verifier: bool

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("validation report requires checks")
        if not all(isinstance(check, ValidationCheck) for check in self.checks):
            raise TypeError("checks must contain ValidationCheck values")
        if not isinstance(self.passed, bool) or not isinstance(
            self.requires_directed_verifier, bool
        ):
            raise TypeError("validation report flags must be bool")


def validate_candidate(
    before: str,
    after: str,
    plan: RepairPlan,
    diff: DiffGuardResult,
) -> ValidationReport:
    if not isinstance(plan, RepairPlan):
        raise TypeError("plan must be RepairPlan")
    if not isinstance(diff, DiffGuardResult):
        raise TypeError("diff must be DiffGuardResult")
    checks = [
        _compile_check(after),
        _scope_check(diff),
        _scene_risk_check(before, after, diff),
    ]
    checks.extend(_geometry_checks(before, after, plan))
    checks.extend(_predicate_checks(after, plan))
    failed = any(check.status is ValidationStatus.FAIL for check in checks)
    unresolved = any(check.status is ValidationStatus.UNRESOLVED for check in checks)
    return ValidationReport(
        checks=tuple(checks),
        passed=not failed and not unresolved,
        requires_directed_verifier=unresolved and not failed,
    )


def _compile_check(code: str) -> ValidationCheck:
    try:
        compile(code, "candidate.py", "exec")
    except SyntaxError as error:
        return ValidationCheck("compile", ValidationStatus.FAIL, error.msg)
    return ValidationCheck("compile", ValidationStatus.PASS, "candidate compiles")


def _scope_check(diff: DiffGuardResult) -> ValidationCheck:
    if diff.passed:
        return ValidationCheck("diff_scope", ValidationStatus.PASS, "scope is valid")
    detail = "; ".join(diff.violations)
    return ValidationCheck("diff_scope", ValidationStatus.FAIL, detail)


def _geometry_checks(
    before: str, after: str, plan: RepairPlan
) -> list[ValidationCheck]:
    baseline = extract_deterministic_logic_facts(before)
    candidate = extract_deterministic_logic_facts(after)
    regressions = [
        key.removesuffix("_count")
        for key, value in candidate.items()
        if key.endswith("_mismatch_count")
        and isinstance(value, int)
        and value > int(baseline.get(key, 0))
    ]
    if regressions:
        detail = f"new deterministic mismatch: {', '.join(sorted(regressions))}"
        global_check = ValidationCheck("geometry", ValidationStatus.FAIL, detail)
    else:
        global_check = ValidationCheck(
            "geometry", ValidationStatus.PASS, "no new deterministic mismatch"
        )
    targeted = [
        ValidationCheck(
            "geometry_resolution",
            ValidationStatus.PASS if resolved else ValidationStatus.FAIL,
            detail,
            issue_id,
        )
        for issue_id, resolved, detail in targeted_geometry_results(
            baseline, candidate, plan
        )
    ]
    return [global_check, *targeted]


def _scene_risk_check(
    before: str, after: str, diff: DiffGuardResult
) -> ValidationCheck:
    risks = new_scene_risks(before, after, diff) if diff.passed else ()
    if risks:
        return ValidationCheck(
            "scene_risk",
            ValidationStatus.FAIL,
            f"new Scene risk: {', '.join(risks)}",
        )
    return ValidationCheck("scene_risk", ValidationStatus.PASS, "no new Scene risk")


def _predicate_checks(code: str, plan: RepairPlan) -> list[ValidationCheck]:
    return [
        _predicate_check(code, issue.issue_id, predicate)
        for issue in plan.issues
        for predicate in issue.acceptance_predicates
    ]


def _predicate_check(
    code: str, issue_id: str, predicate: Mapping[str, object]
) -> ValidationCheck:
    kind = str(predicate.get("kind") or predicate.get("predicate") or "").strip()
    value = predicate.get("value")
    if kind not in _PRESENT_KINDS | _ABSENT_KINDS or not isinstance(value, str):
        return ValidationCheck(
            "acceptance_predicate",
            ValidationStatus.UNRESOLVED,
            "predicate requires directed verification",
            issue_id,
        )
    bound = predicate_has_bound_evidence(
        code,
        kind=kind,
        value=value,
        scene_id=predicate.get("scene_id"),
    )
    if bound is not None:
        status = ValidationStatus.PASS if bound else ValidationStatus.UNRESOLVED
        detail = f"{kind} {'has bound evidence' if bound else 'lacks bound evidence'}"
        return ValidationCheck("acceptance_predicate", status, detail, issue_id)
    haystack = _predicate_scope(code, predicate.get("scene_id"))
    present = value in haystack
    passed = present if kind in _PRESENT_KINDS else not present
    status = ValidationStatus.PASS if passed else ValidationStatus.FAIL
    detail = f"{kind} {'passed' if passed else 'failed'}"
    return ValidationCheck("acceptance_predicate", status, detail, issue_id)


def _predicate_scope(code: str, scene_id: object) -> str:
    if not isinstance(scene_id, str) or not scene_id.strip():
        return code
    for scene in extract_scenes(code):
        if scene.scene_id == scene_id:
            lines = code.splitlines()
            return "\n".join(lines[scene.line_start - 1 : scene.line_end])
    return ""
