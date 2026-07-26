"""Pure guards used by the bounded Quality Operator session."""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence

from manim_quality.layout.policy import layout_invariant_fingerprint
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
        if item.category is not expected:
            raise ValueError(f"finding category does not match {scope} patch")


def validate_patch_budget_raise(current: int, requested: int) -> None:
    if type(requested) is not int:
        raise TypeError("max_patch_attempts must be an integer")
    if requested < current:
        raise InvalidSessionTransition("patch budget can only be raised")


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
        return 5
    if blocking_count <= 8:
        return 6
    return 7


def require_blocking_findings_repaired(
    findings: Mapping[str, Finding],
    attempts: Sequence[CandidateAttempt],
) -> None:
    blocking = {
        item.finding_id
        for item in findings.values()
        if item.severity == "blocking"
    }
    repaired = {
        finding_id
        for attempt in attempts[1:]
        for finding_id in attempt.finding_ids
    }
    if not blocking.issubset(repaired):
        raise InvalidSessionTransition(
            "blocking findings require a validated repair revision"
        )


def verify_candidate(
    *,
    problem_text: str,
    baseline: CandidateAttempt,
    current: CandidateAttempt,
    embedded_hash: str | None,
    code: str,
    scope: PatchScope,
) -> None:
    if problem_text in baseline.code and problem_text not in code:
        raise ProblemLockViolation("patch changed the locked problem text")
    if (
        embedded_hash is not None
        and embedded_problem_hash(code, problem_text) != embedded_hash
    ):
        raise ProblemLockViolation("patch changed the embedded problem source")
    compile(code, "candidate.py", "exec")
    if (
        scope is PatchScope.LAYOUT
        and layout_invariant_fingerprint(code)
        != layout_invariant_fingerprint(current.code)
    ):
        raise ScopeViolation("layout patch changed the semantic invariant")


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
