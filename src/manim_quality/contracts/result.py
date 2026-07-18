"""Versioned quality decision returned to generation callers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ._validation import (
    freeze_non_negative_int_mapping,
    freeze_string_sequence,
    require_enum,
    require_non_empty_string,
    require_optional_string,
    require_wire_array,
    require_wire_object,
    validate_contract_dict,
)

RESULT_SCHEMA_VERSION = 1


class DeliveryDecision(StrEnum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_WARNING = "ACCEPT_WITH_WARNING"
    REGENERATE = "REGENERATE"
    HOLD = "HOLD"
    FAILED = "FAILED"


_DELIVERY_DECISIONS = frozenset(
    {DeliveryDecision.ACCEPT, DeliveryDecision.ACCEPT_WITH_WARNING}
)
_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "decision",
        "accepted_revision_id",
        "final_code_ref",
        "final_render_manifest_ref",
        "certificate_ref",
        "warnings",
        "token_usage",
        "timings_ms",
    }
)


@dataclass(frozen=True, slots=True)
class QualityResult:
    """Delivery evidence is required only for accepted decisions.

    Non-delivery decisions may retain a certificate reference describing failure,
    hold, or regeneration evidence, but cannot expose accepted or final artifacts.
    """

    job_id: str
    decision: DeliveryDecision
    accepted_revision_id: str | None
    final_code_ref: str | None
    final_render_manifest_ref: str | None
    certificate_ref: str | None
    warnings: Sequence[str]
    token_usage: Mapping[str, int]
    timings_ms: Mapping[str, int]
    schema_version: int = field(default=RESULT_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        require_non_empty_string(self.job_id, "job_id")
        object.__setattr__(
            self,
            "decision",
            require_enum(self.decision, DeliveryDecision, "decision"),
        )
        object.__setattr__(
            self,
            "warnings",
            freeze_string_sequence(self.warnings, "warnings"),
        )
        self._validate_delivery_fields()
        object.__setattr__(
            self,
            "token_usage",
            freeze_non_negative_int_mapping(self.token_usage, "token_usage"),
        )
        object.__setattr__(
            self,
            "timings_ms",
            freeze_non_negative_int_mapping(self.timings_ms, "timings_ms"),
        )

    def _validate_delivery_fields(self) -> None:
        field_values = {
            "accepted_revision_id": self.accepted_revision_id,
            "final_code_ref": self.final_code_ref,
            "final_render_manifest_ref": self.final_render_manifest_ref,
        }
        if self.decision in _DELIVERY_DECISIONS:
            if self.decision is DeliveryDecision.ACCEPT and self.warnings:
                raise ValueError("ACCEPT requires warnings to be empty")
            if (
                self.decision is DeliveryDecision.ACCEPT_WITH_WARNING
                and not self.warnings
            ):
                raise ValueError("ACCEPT_WITH_WARNING requires non-empty warnings")
            for name, value in field_values.items():
                if value is None:
                    raise ValueError(f"{name} is required for {self.decision.value}")
                require_non_empty_string(value, name)
            if self.certificate_ref is None:
                raise ValueError(
                    f"certificate_ref is required for {self.decision.value}"
                )
            require_non_empty_string(self.certificate_ref, "certificate_ref")
            return
        for name, value in field_values.items():
            if value is not None:
                raise ValueError(f"{name} is forbidden for {self.decision.value}")
        require_optional_string(self.certificate_ref, "certificate_ref")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "decision": self.decision.value,
            "accepted_revision_id": self.accepted_revision_id,
            "final_code_ref": self.final_code_ref,
            "final_render_manifest_ref": self.final_render_manifest_ref,
            "certificate_ref": self.certificate_ref,
            "warnings": list(self.warnings),
            "token_usage": dict(self.token_usage),
            "timings_ms": dict(self.timings_ms),
        }

    @classmethod
    def from_dict(cls, data: object) -> QualityResult:
        payload = validate_contract_dict(
            data, _FIELDS, RESULT_SCHEMA_VERSION, cls.__name__
        )
        return cls(
            job_id=payload["job_id"],  # type: ignore[arg-type]
            decision=require_enum(payload["decision"], DeliveryDecision, "decision"),
            accepted_revision_id=payload["accepted_revision_id"],  # type: ignore[arg-type]
            final_code_ref=payload["final_code_ref"],  # type: ignore[arg-type]
            final_render_manifest_ref=payload["final_render_manifest_ref"],  # type: ignore[arg-type]
            certificate_ref=payload["certificate_ref"],  # type: ignore[arg-type]
            warnings=require_wire_array(payload["warnings"], "warnings"),
            token_usage=require_wire_object(payload["token_usage"], "token_usage"),
            timings_ms=require_wire_object(payload["timings_ms"], "timings_ms"),
        )
