"""Pure guards used by the bounded Quality Operator session."""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence

from manim_quality.revisions.fingerprint import sha256_text

from .models import CandidateAttempt, Finding, FindingCategory, PatchScope
from .problem_source import extract_problem_text
from .session_errors import (
    InvalidSessionTransition,
    ProblemLockViolation,
    ScopeViolation,
)


def validate_finding_scope(
    findings: Mapping[str, Finding],
    scope: PatchScope,
    finding_ids: tuple[str, ...],
) -> None:
    if not finding_ids:
        raise ValueError("patch requires at least one finding_id")
    expected = FindingCategory(scope.value)
    for finding_id in finding_ids:
        item = findings.get(finding_id)
        if item is None:
            raise ValueError(f"unknown finding_id: {finding_id}")
        if expected is FindingCategory.LAYOUT and item.category is not expected:
            raise ValueError(f"finding category does not match {scope} patch")


def validate_patch_budget_raise(current: int, requested: int) -> None:
    if type(requested) is not int:
        raise TypeError("max_patch_attempts must be an integer")
    if requested < current:
        raise InvalidSessionTransition("patch budget can only be raised")


def validate_patch_transition(
    *,
    findings: Mapping[str, Finding],
    attempts: Sequence[CandidateAttempt],
    validations: Mapping[str, object],
    current: CandidateAttempt,
    max_patch_attempts: int,
    finding_batches: int,
    scope: PatchScope,
    finding_ids: tuple[str, ...],
) -> None:
    if not isinstance(scope, PatchScope):
        raise TypeError("scope must be a PatchScope")
    if finding_batches == 0:
        raise InvalidSessionTransition("findings must be recorded before patch")
    if len(attempts) - 1 >= max_patch_attempts:
        raise InvalidSessionTransition("patch attempt budget exhausted")
    current_validation = validations.get(current.revision_id)
    if current.revision_id != "R0":
        if current_validation is None:
            raise InvalidSessionTransition("current revision must be validated")
        if not getattr(current_validation, "improved", False):
            raise InvalidSessionTransition("previous revision did not improve")
    validate_finding_scope(findings, scope, finding_ids)


def validate_session_patch(
    session, scope: PatchScope, finding_ids: tuple[str, ...]
) -> None:
    validate_patch_transition(
        findings=session._findings,
        attempts=session._attempts,
        validations=session._validations,
        current=session.current_revision,
        max_patch_attempts=session._max_patch_attempts,
        finding_batches=session._finding_batches,
        scope=scope,
        finding_ids=finding_ids,
    )


def validate_recovery_revision(
    target: CandidateAttempt,
    current: CandidateAttempt,
    validations: Mapping[str, object],
) -> None:
    if target.revision_id == current.revision_id:
        return
    if target.revision_id == "R0":
        return
    record = validations.get(target.revision_id)
    if record is None or not getattr(record, "passed", False):
        raise ValueError(
            "recovery target must be the baseline or a validated passing revision"
        )


def validate_patch_text(old_text: str, new_text: str) -> None:
    if old_text == new_text:
        raise ValueError("patch must change content")
    if len(old_text) > 200 and len(new_text) * 2 < len(old_text):
        raise ScopeViolation("patch removes too much content in one block")


def validate_layout_inspection(fingerprint: str, blocking_count: int) -> None:
    if (
        not isinstance(fingerprint, str)
        or not fingerprint.startswith("sha256:")
        or len(fingerprint) != 71
    ):
        raise ValueError("fingerprint must be a sha256 digest")
    if (
        isinstance(blocking_count, bool)
        or not isinstance(blocking_count, int)
        or blocking_count < 0
    ):
        raise ValueError("blocking_count must be a non-negative integer")


def best_validated_revision(
    attempts: Sequence[CandidateAttempt],
    validations: Mapping[str, object],
    inspections: Mapping[str, tuple[str, int]],
) -> dict[str, object] | None:
    """Latest render-passing candidate with the lowest known blocking count.

    The result is evidence, not a deliverable: it may still carry blocking
    layout issues or lack a layout inspection entirely.
    """

    best_key: tuple[int, int] | None = None
    best_id: str | None = None
    for index, attempt in enumerate(attempts[1:], start=1):
        record = validations.get(attempt.revision_id)
        if record is None or not getattr(record, "passed", False):
            continue
        inspection = inspections.get(attempt.revision_id)
        blocking = inspection[1] if inspection is not None else 10**9
        key = (blocking, -index)
        if best_key is None or key < best_key:
            best_key = key
            best_id = attempt.revision_id
    if best_id is None:
        return None
    inspection = inspections.get(best_id)
    return {
        "revision_id": best_id,
        "blocking_count": None if inspection is None else inspection[1],
        "layout_inspected": inspection is not None,
    }


def patch_budget_for_blocking(blocking_count: int) -> int:
    """Scale the patch budget to the baseline blocking pressure."""

    if isinstance(blocking_count, bool) or not isinstance(blocking_count, int):
        raise TypeError("blocking_count must be an integer")
    if blocking_count <= 2:
        return 12
    if blocking_count <= 8:
        return 16
    return 20


def require_blocking_findings_repaired(
    findings: Mapping[str, Finding],
    attempts: Sequence[CandidateAttempt],
    validations: Mapping[str, object],
    current_revision_id: str,
) -> None:
    blocking = {
        item.finding_id
        for item in findings.values()
        if item.severity == "blocking"
    }
    repaired = validated_repaired_finding_ids(
        attempts, validations, current_revision_id
    )
    if not blocking.issubset(repaired):
        raise InvalidSessionTransition(
            "blocking findings require a validated repair revision"
        )


def validated_repaired_finding_ids(
    attempts: Sequence[CandidateAttempt],
    validations: Mapping[str, object],
    current_revision_id: str,
) -> set[str]:
    return {
        finding_id
        for attempt in _revision_lineage(attempts, current_revision_id)
        if getattr(validations.get(attempt.revision_id), "passed", False)
        for finding_id in attempt.finding_ids
    }


def _revision_lineage(
    attempts: Sequence[CandidateAttempt],
    current_revision_id: str,
) -> tuple[CandidateAttempt, ...]:
    by_id = {item.revision_id: item for item in attempts}
    lineage = []
    revision = by_id[current_revision_id]
    while revision.parent_revision_id is not None:
        lineage.append(revision)
        revision = by_id[revision.parent_revision_id]
    return tuple(reversed(lineage))


def verify_candidate(
    *,
    problem_text: str,
    baseline: CandidateAttempt,
    embedded_hash: str | None,
    code: str,
) -> None:
    if problem_text in baseline.code and problem_text not in code:
        raise ProblemLockViolation("patch changed the locked problem text")
    if (
        embedded_hash is not None
        and embedded_problem_hash(code, problem_text) != embedded_hash
    ):
        raise ProblemLockViolation("patch changed the embedded problem source")
    compile(code, "candidate.py", "exec")


def patch_hash(before: str, after: str) -> str:
    patch = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="before.py",
            tofile="after.py",
        )
    )
    return sha256_text(patch)


def embedded_problem_hash(code: str, expected: str) -> str | None:
    try:
        extracted = extract_problem_text(code)
    except ValueError:
        return None
    if extracted.strip() != expected.strip():
        return None
    return sha256_text(extracted.strip())
