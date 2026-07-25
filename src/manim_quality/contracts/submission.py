"""Versioned input contract for quality evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from ._formats import require_callback_url
from ._json_values import (
    freeze_json_object,
    freeze_wire_json_object,
    thaw_json_object,
)
from ._validation import (
    require_non_empty_string,
    require_optional_string,
    validate_contract_dict,
)

SUBMISSION_SCHEMA_VERSION = 1
_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "tenant_id",
        "candidate_code_ref",
        "problem_text",
        "planning",
        "expected_answer",
        "render_manifest_ref",
        "asset_manifest_ref",
        "callback_url",
        "idempotency_key",
    }
)


@dataclass(frozen=True, slots=True)
class QualitySubmission:
    job_id: str
    tenant_id: str
    candidate_code_ref: str
    problem_text: str
    planning: Mapping[str, object]
    expected_answer: str | None
    render_manifest_ref: str | None
    asset_manifest_ref: str | None
    callback_url: str | None
    idempotency_key: str
    schema_version: int = field(default=SUBMISSION_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        require_non_empty_string(self.job_id, "job_id")
        require_non_empty_string(self.tenant_id, "tenant_id")
        require_non_empty_string(self.candidate_code_ref, "candidate_code_ref")
        require_non_empty_string(self.problem_text, "problem_text")
        require_optional_string(
            self.expected_answer, "expected_answer", allow_empty=True
        )
        require_optional_string(self.render_manifest_ref, "render_manifest_ref")
        require_optional_string(self.asset_manifest_ref, "asset_manifest_ref")
        require_callback_url(self.callback_url, "callback_url")
        require_non_empty_string(self.idempotency_key, "idempotency_key")
        object.__setattr__(
            self,
            "planning",
            freeze_json_object(self.planning, "planning"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "candidate_code_ref": self.candidate_code_ref,
            "problem_text": self.problem_text,
            "planning": thaw_json_object(self.planning),
            "expected_answer": self.expected_answer,
            "render_manifest_ref": self.render_manifest_ref,
            "asset_manifest_ref": self.asset_manifest_ref,
            "callback_url": self.callback_url,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: object) -> QualitySubmission:
        payload = validate_contract_dict(
            data, _FIELDS, SUBMISSION_SCHEMA_VERSION, cls.__name__
        )
        return cls(
            job_id=payload["job_id"],  # type: ignore[arg-type]
            tenant_id=payload["tenant_id"],  # type: ignore[arg-type]
            candidate_code_ref=payload["candidate_code_ref"],  # type: ignore[arg-type]
            problem_text=payload["problem_text"],  # type: ignore[arg-type]
            planning=freeze_wire_json_object(payload["planning"], "planning"),
            expected_answer=payload["expected_answer"],  # type: ignore[arg-type]
            render_manifest_ref=payload["render_manifest_ref"],  # type: ignore[arg-type]
            asset_manifest_ref=payload["asset_manifest_ref"],  # type: ignore[arg-type]
            callback_url=payload["callback_url"],  # type: ignore[arg-type]
            idempotency_key=payload["idempotency_key"],  # type: ignore[arg-type]
        )


class GenerationAdapter(Protocol):
    async def regenerate(
        self,
        submission: QualitySubmission,
        failure_evidence_ref: str,
    ) -> QualitySubmission: ...
