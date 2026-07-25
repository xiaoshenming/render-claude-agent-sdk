"""Pure guards used by the bounded Quality Operator session."""

from __future__ import annotations

import difflib
from collections.abc import Mapping

from manim_quality.layout.policy import layout_invariant_fingerprint
from manim_quality.revisions.fingerprint import sha256_text

from .models import CandidateAttempt, Finding, FindingCategory, PatchScope
from .problem_source import extract_problem_text
from .session_errors import ProblemLockViolation, ScopeViolation


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
