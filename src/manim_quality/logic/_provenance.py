"""Immutable source provenance used by compact logic evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from manim_quality.contracts import QualitySubmission
from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._json_values import freeze_json_object, thaw_json_object
from manim_quality.contracts._validation import require_non_empty_string
from manim_quality.revisions.fingerprint import sha256_text


@dataclass(frozen=True, slots=True)
class ProvenancedValue:
    value: object
    source_ref: str
    content_hash: str

    def __post_init__(self) -> None:
        if isinstance(self.value, Mapping):
            object.__setattr__(self, "value", freeze_json_object(self.value, "value"))
        elif type(self.value) is not str:
            raise TypeError("provenanced value must be text or a JSON object")
        require_non_empty_string(self.source_ref, "source_ref")
        require_sha256(self.content_hash, "content_hash")

    def to_prompt_dict(self) -> dict[str, object]:
        value = self.value
        if isinstance(value, Mapping):
            value = thaw_json_object(value)
        return {"value": value}


def canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        thaw_json_object(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def text_provenance(
    submission: QualitySubmission, field: str, value: str
) -> ProvenancedValue:
    return ProvenancedValue(
        value=value,
        source_ref=f"submission:{submission.job_id}:{field}",
        content_hash=sha256_text(value),
    )


def planning_provenance(submission: QualitySubmission) -> ProvenancedValue:
    content = canonical_json(submission.planning)
    return ProvenancedValue(
        value=submission.planning,
        source_ref=f"submission:{submission.job_id}:planning",
        content_hash=sha256_text(content),
    )
