"""Immutable domain models for one bounded Quality Operator run."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from manim_quality.contracts._json_values import freeze_json_object, thaw_json_object
from manim_quality.revisions.fingerprint import sha256_text


class FindingCategory(StrEnum):
    LOGIC = "logic"
    LAYOUT = "layout"


class PatchScope(StrEnum):
    LOGIC = "logic"
    LAYOUT = "layout"


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    category: FindingCategory
    severity: str
    summary: str
    acceptance_criteria: str
    depends_on_finding_ids: tuple[str, ...] = ()
    affected_symbols: tuple[str, ...] = ()
    source_reviewer_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.finding_id, "finding_id")
        if not isinstance(self.category, FindingCategory):
            raise TypeError("category must be a FindingCategory")
        if self.severity not in {"blocking", "warning"}:
            raise ValueError("severity must be blocking or warning")
        _require_text(self.summary, "summary")
        _require_text(self.acceptance_criteria, "acceptance_criteria")
        _require_text_tuple(
            self.depends_on_finding_ids, "depends_on_finding_ids"
        )
        _require_text_tuple(self.affected_symbols, "affected_symbols")
        _require_text_tuple(self.source_reviewer_ids, "source_reviewer_ids")


@dataclass(frozen=True, slots=True)
class CandidateAttempt:
    revision_id: str
    parent_revision_id: str | None
    scope: PatchScope | None
    code: str
    code_hash: str
    patch_hash: str | None
    finding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.revision_id, "revision_id")
        if self.parent_revision_id is not None:
            _require_text(self.parent_revision_id, "parent_revision_id")
        if self.scope is not None and not isinstance(self.scope, PatchScope):
            raise TypeError("scope must be a PatchScope or None")
        _require_text(self.code, "code")
        _require_sha256(self.code_hash, "code_hash")
        if self.patch_hash is not None:
            _require_sha256(self.patch_hash, "patch_hash")
        if not isinstance(self.finding_ids, tuple):
            raise TypeError("finding_ids must be a tuple")


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    revision_id: str
    passed: bool
    improved: bool
    fingerprint: str

    def __post_init__(self) -> None:
        _require_text(self.revision_id, "revision_id")
        if not isinstance(self.passed, bool) or not isinstance(self.improved, bool):
            raise TypeError("passed and improved must be booleans")
        _require_sha256(self.fingerprint, "fingerprint")


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    passed: bool
    improved: bool
    summary: str
    details: Mapping[str, object]
    revision_id: str
    code_hash: str
    problem_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool) or not isinstance(self.improved, bool):
            raise TypeError("passed and improved must be booleans")
        _require_text(self.summary, "summary")
        _require_text(self.revision_id, "revision_id")
        _require_sha256(self.code_hash, "code_hash")
        _require_sha256(self.problem_hash, "problem_hash")
        object.__setattr__(
            self,
            "details",
            freeze_json_object(self.details, "validation_details"),
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "passed": self.passed,
            "improved": self.improved,
            "summary": self.summary,
            "details": thaw_json_object(self.details),
            "revision_id": self.revision_id,
            "code_hash": self.code_hash,
            "problem_hash": self.problem_hash,
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256_text(text)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
    ):
        raise ValueError(f"{name} must be a sha256 digest")
    return value


def _require_text_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")
    for item in value:
        _require_text(item, name)
    return value
