"""Stable persisted identity for one real revision render."""

from __future__ import annotations

import hashlib
from pathlib import Path

from manim_quality.operator.models import CandidateAttempt

from .models import RenderResult


def validation_report(
    revision: CandidateAttempt,
    problem_hash: str,
    result: RenderResult,
    details: dict[str, object],
) -> dict[str, object]:
    summary = "real Manim render passed" if result.ok else "real Manim render failed"
    return {
        "schema_version": "manim-quality.validation-report.v1",
        "passed": result.ok,
        "improved": result.ok,
        "summary": summary,
        "revision_id": revision.revision_id,
        "code_hash": revision.code_hash,
        "problem_hash": problem_hash,
        "video_sha256": _video_sha256(result.video_path),
        "details": dict(details),
        # Keep the historical flattened diagnostics for human/debug readers.
        **details,
    }


def _video_sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
