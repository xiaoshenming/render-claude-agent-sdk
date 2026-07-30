from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

GRADES = ("A", "B", "C", "D", "E")


@dataclass(frozen=True, slots=True)
class Candidate:
    revision_id: str
    source_sha256: str
    video_sha256: str
    source_path: str
    video_path: str

    def __post_init__(self) -> None:
        if not all(asdict(self).values()):
            raise ValueError("candidate fields must be non-empty")


@dataclass(frozen=True, slots=True)
class AssuranceOutcome:
    grade: str
    status: str
    issues: tuple[dict[str, Any], ...] = ()
    usage: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.grade not in GRADES:
            raise ValueError("grade must be A, B, C, D, or E")


@dataclass(frozen=True, slots=True)
class PassRecord:
    assurance_pass: int
    candidate: Candidate
    outcome: AssuranceOutcome


@dataclass(frozen=True, slots=True)
class LoopState:
    initial_candidate: Candidate
    current_candidate: Candidate
    best_candidate: Candidate
    best_grade: str | None = None
    assurance_passes: int = 0
    repair_rounds: int = 0
    records: tuple[PassRecord, ...] = ()
    pending_issues: tuple[dict[str, Any], ...] = ()
    terminal_reason: str | None = None

    @classmethod
    def initial(cls, candidate: Candidate) -> LoopState:
        return cls(candidate, candidate, candidate)


@dataclass(frozen=True, slots=True)
class LoopResult:
    final_candidate: Candidate
    final_grade: str | None
    assurance_passes: int
    repair_rounds: int
    terminal_reason: str
    records: tuple[PassRecord, ...]
