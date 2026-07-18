"""Bind model citation claims to exact platform-owned source artifacts."""

from __future__ import annotations

from collections.abc import Mapping

from manim_quality.contracts._validation import require_non_empty_string

from ._errors import ReviewBindingInvariantError, ReviewOutputValidationError
from ._provenance import canonical_json
from .evidence import LogicEvidence
from .schemas import CitationArtifact, EvidenceCitation

_FIELDS = frozenset({"artifact", "scene_id", "line_start", "line_end", "excerpt"})


def bind_citation(
    value: object,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> EvidenceCitation:
    data = _exact_object(value)
    artifact = _artifact(data["artifact"])
    excerpt = _required_text(data["excerpt"], "excerpt")
    scene_id = _optional_text(data["scene_id"], "scene_id")
    line_start = _optional_int(data["line_start"], "line_start")
    line_end = _optional_int(data["line_end"], "line_end")
    source_ref, source_hash, source = _source_for(
        artifact, evidence, candidate_code, render_manifest_text
    )
    if artifact is CitationArtifact.CANDIDATE_CODE:
        _verify_code_excerpt(
            excerpt, scene_id, line_start, line_end, evidence, candidate_code
        )
    else:
        if any(value is not None for value in (scene_id, line_start, line_end)):
            raise ReviewOutputValidationError(
                "non-code citations cannot declare code locations"
            )
        if excerpt not in source:
            raise ReviewOutputValidationError(
                f"citation excerpt is absent from {artifact.value}"
            )
    return EvidenceCitation(
        artifact=artifact,
        source_ref=source_ref,
        source_hash=source_hash,
        excerpt=excerpt,
        scene_id=scene_id,
        line_start=line_start,
        line_end=line_end,
    )


def _source_for(
    artifact: CitationArtifact,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> tuple[str, str, str]:
    if artifact is CitationArtifact.CANDIDATE_CODE:
        return evidence.candidate_ref, evidence.code_hash, candidate_code
    if artifact is CitationArtifact.PROBLEM_TEXT:
        return (
            evidence.problem.source_ref,
            evidence.problem.content_hash,
            str(evidence.problem.value),
        )
    if artifact is CitationArtifact.PLANNING:
        planning = evidence.planning.value
        if not isinstance(planning, Mapping):
            raise ReviewBindingInvariantError("planning evidence must be an object")
        return (
            evidence.planning.source_ref,
            evidence.planning.content_hash,
            canonical_json(planning),
        )
    if artifact is CitationArtifact.EXPECTED_ANSWER:
        if evidence.expected_answer is None:
            raise ReviewOutputValidationError("expected_answer citation has no source")
        return (
            evidence.expected_answer.source_ref,
            evidence.expected_answer.content_hash,
            str(evidence.expected_answer.value),
        )
    return (
        evidence.render_manifest_ref,
        evidence.render_manifest_hash,
        render_manifest_text,
    )


def _verify_code_excerpt(
    excerpt: str,
    scene_id: str | None,
    line_start: int | None,
    line_end: int | None,
    evidence: LogicEvidence,
    candidate_code: str,
) -> None:
    if type(line_start) is not int or type(line_end) is not int:
        raise ReviewOutputValidationError(
            "candidate_code citations require line bounds"
        )
    lines = candidate_code.splitlines()
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        raise ReviewOutputValidationError(
            "candidate_code citation line bounds are invalid"
        )
    if scene_id is not None:
        scene = next(
            (item for item in evidence.scenes if item.scene_id == scene_id), None
        )
        if scene is None or line_start < scene.line_start or line_end > scene.line_end:
            raise ReviewOutputValidationError(
                "candidate_code citation falls outside its Scene"
            )
    if excerpt not in "\n".join(lines[line_start - 1 : line_end]):
        raise ReviewOutputValidationError(
            "candidate_code citation excerpt is not present at declared lines"
        )


def _exact_object(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise ReviewOutputValidationError("citation must be an object with string keys")
    if value.keys() != _FIELDS:
        raise ReviewOutputValidationError("citation fields do not match schema")
    return value


def _artifact(value: object) -> CitationArtifact:
    if type(value) is not str:
        raise ReviewOutputValidationError("artifact must be a string")
    try:
        return CitationArtifact(value)
    except ValueError as error:
        raise ReviewOutputValidationError(
            f"artifact has invalid value {value!r}"
        ) from error


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _required_text(value, name)


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise ReviewOutputValidationError(f"{name} must be an integer or null")
    return value


def _required_text(value: object, name: str) -> str:
    try:
        return require_non_empty_string(value, name)
    except (TypeError, ValueError) as error:
        raise ReviewOutputValidationError(str(error)) from error
