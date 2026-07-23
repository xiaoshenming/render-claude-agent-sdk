"""Typed outcomes and ports used by the bounded logic repair flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RepairFlowStatus(StrEnum):
    CANDIDATE_READY = "candidate_ready"
    CANDIDATE_RISK = "candidate_risk"
    REJECTED = "rejected"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True, slots=True)
class LogicRepairFlowResult:
    status: RepairFlowStatus
    attempt_count: int
    patch_hashes: tuple[str, ...]
    candidate_code: str | None
    requires_render: bool
    reason: str


class AttemptStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    REJECTED = "rejected"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    status: AttemptStatus
    patch_hash: str | None = None
    candidate_code: str | None = None
    resolved_issue_ids: tuple[str, ...] = ()
    review_gaps: tuple[str, ...] = ()
    reason: str = ""


class CoderPort(Protocol):
    def patch(self, **kwargs): ...


class VerifierPort(Protocol):
    def verify(self, **kwargs): ...
