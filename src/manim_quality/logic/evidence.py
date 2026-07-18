"""Compact, provenance-bound evidence for read-only logic review."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from manim_quality.contracts import QualitySubmission, Revision
from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.contracts._validation import require_non_empty_string
from manim_quality.revisions.fingerprint import code_hash as calculate_code_hash
from manim_quality.revisions.fingerprint import evidence_hash

from ._errors import EvidenceBuildError
from ._provenance import (
    ProvenancedValue,
    canonical_json,
    planning_provenance,
    text_provenance,
)
from ._scene_evidence import SceneDigest, extract_scenes
from .engine_adapter import (
    validate_engine_review_evidence,
    verify_engine_review_evidence,
)

__all__ = [
    "EvidenceBuildError",
    "LogicEvidence",
    "ProvenancedValue",
    "SceneDigest",
    "build_logic_evidence",
    "canonical_json",
]


@dataclass(frozen=True, slots=True)
class LogicEvidence:
    revision_id: str
    candidate_ref: str
    code_hash: str
    render_manifest_ref: str
    render_manifest_hash: str
    problem: ProvenancedValue
    planning: ProvenancedValue
    expected_answer: ProvenancedValue | None
    engine_evidence: Mapping[str, object]
    scenes: Sequence[SceneDigest]

    def __post_init__(self) -> None:
        require_non_empty_string(self.revision_id, "revision_id")
        require_non_empty_string(self.candidate_ref, "candidate_ref")
        require_sha256(self.code_hash, "code_hash")
        require_non_empty_string(self.render_manifest_ref, "render_manifest_ref")
        require_sha256(self.render_manifest_hash, "render_manifest_hash")
        for name in ("problem", "planning"):
            if not isinstance(getattr(self, name), ProvenancedValue):
                raise TypeError(f"{name} must be ProvenancedValue")
        if not isinstance(self.planning.value, Mapping):
            raise TypeError("planning evidence must be an object")
        if self.expected_answer is not None and not isinstance(
            self.expected_answer, ProvenancedValue
        ):
            raise TypeError("expected_answer must be ProvenancedValue or None")
        object.__setattr__(
            self,
            "engine_evidence",
            validate_engine_review_evidence(
                self.engine_evidence, expected_code_hash=self.code_hash
            ),
        )
        scenes = tuple(self.scenes)
        if not scenes or not all(isinstance(scene, SceneDigest) for scene in scenes):
            raise ValueError("evidence requires at least one Scene digest")
        if len({scene.scene_id for scene in scenes}) != len(scenes):
            raise ValueError("scene_id values must be unique")
        object.__setattr__(self, "scenes", scenes)

    def to_prompt_dict(self) -> dict[str, object]:
        engine_evidence = thaw_json_object(self.engine_evidence)
        engine_evidence.pop("candidate_code_hash", None)
        engine_evidence.pop("extractor_identity", None)
        return {
            "problem": self.problem.to_prompt_dict(),
            "planning": self.planning.to_prompt_dict(),
            "expected_answer": (
                self.expected_answer.to_prompt_dict()
                if self.expected_answer is not None
                else None
            ),
            "engine_evidence": engine_evidence,
            "scenes": [scene.to_prompt_dict() for scene in self.scenes],
        }


def build_logic_evidence(
    *,
    code: str,
    submission: QualitySubmission,
    revision: Revision,
    render_manifest: bytes,
    engine_evidence: Mapping[str, object],
) -> LogicEvidence:
    if not isinstance(submission, QualitySubmission):
        raise TypeError("submission must be QualitySubmission")
    if not isinstance(revision, Revision):
        raise TypeError("revision must be Revision")
    actual_code_hash = calculate_code_hash(code)
    if revision.code_hash != actual_code_hash:
        raise EvidenceBuildError("candidate code hash does not match revision")
    if submission.render_manifest_ref is None:
        raise EvidenceBuildError("render_manifest_ref is required for logic review")
    _require_json_manifest(render_manifest)
    actual_manifest_hash = evidence_hash(render_manifest)
    if revision.render_manifest_hash != actual_manifest_hash:
        raise EvidenceBuildError("render manifest hash does not match revision")
    verified_engine_evidence = verify_engine_review_evidence(code, engine_evidence)
    return LogicEvidence(
        revision_id=revision.revision_id,
        candidate_ref=submission.candidate_code_ref,
        code_hash=actual_code_hash,
        render_manifest_ref=submission.render_manifest_ref,
        render_manifest_hash=actual_manifest_hash,
        problem=text_provenance(submission, "problem_text", submission.problem_text),
        planning=planning_provenance(submission),
        expected_answer=(
            text_provenance(submission, "expected_answer", submission.expected_answer)
            if submission.expected_answer is not None
            else None
        ),
        engine_evidence=verified_engine_evidence,
        scenes=extract_scenes(code),
    )


def _require_json_manifest(content: bytes) -> None:
    if not isinstance(content, bytes):
        raise TypeError("render_manifest must be bytes")
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        message = "render manifest must be a UTF-8 JSON object"
        raise EvidenceBuildError(message) from error
    if type(value) is not dict:
        raise EvidenceBuildError("render manifest must be a JSON object")
