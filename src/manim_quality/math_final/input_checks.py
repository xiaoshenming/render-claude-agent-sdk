from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InputEvidence:
    code: str
    status: str
    detail: str
    deterministic: bool = True


def inspect_input_identity(
    *,
    problem_text: str,
    source: str,
    expected_sha256: str | None = None,
) -> tuple[InputEvidence, ...]:
    findings: list[InputEvidence] = []
    if not problem_text.strip():
        findings.append(
            InputEvidence(
                code="MISSING_AUTHORITATIVE_PROBLEM",
                status="source_mismatch",
                detail="AUTHORITATIVE_PROBLEM_TEXT is empty",
            )
        )
    actual_sha = hashlib.sha256(source.encode()).hexdigest()
    if expected_sha256 and actual_sha != expected_sha256.lower():
        findings.append(
            InputEvidence(
                code="SOURCE_SHA_MISMATCH",
                status="source_mismatch",
                detail=f"expected {expected_sha256.lower()}, observed {actual_sha}",
            )
        )
    try:
        compile(source, "candidate.py", "exec")
    except SyntaxError as error:
        findings.append(
            InputEvidence(
                code="SOURCE_NOT_EXECUTABLE",
                status="minor_issue",
                detail=f"line {error.lineno}: {error.msg}",
            )
        )
    return tuple(findings)
