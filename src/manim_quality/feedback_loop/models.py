from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

GRADES = ("A", "B", "C", "D", "E")


@dataclass(frozen=True, slots=True)
class LoopExecutionIdentity:
    """Immutable identity for one resumable feedback-loop execution."""

    job_id: str
    question_sha256: str
    source_sha256: str
    video_sha256: str
    model_id: str
    prompt_version: str
    tool_version: str
    policy_version: str
    runtime_version: str
    schema_version: str

    def __post_init__(self) -> None:
        if not all(asdict(self).values()):
            raise ValueError("execution identity fields must be non-empty")
        for name in ("question_sha256", "source_sha256", "video_sha256"):
            _require_sha256(getattr(self, name), name)

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()


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
    best_issue_score: tuple[int, int] | None = None
    assurance_passes: int = 0
    repair_rounds: int = 0
    coder_calls: int = 0
    bootstrap_completed: bool = False
    execution_identity: LoopExecutionIdentity | None = None
    records: tuple[PassRecord, ...] = ()
    pending_issues: tuple[dict[str, Any], ...] = ()
    terminal_reason: str | None = None

    @classmethod
    def initial(
        cls,
        candidate: Candidate,
        identity: LoopExecutionIdentity | None = None,
    ) -> LoopState:
        return cls(
            candidate,
            candidate,
            candidate,
            execution_identity=identity,
        )


@dataclass(frozen=True, slots=True)
class LoopResult:
    final_candidate: Candidate
    final_grade: str | None
    assurance_passes: int
    repair_rounds: int
    coder_calls: int
    terminal_reason: str
    records: tuple[PassRecord, ...]


def _require_sha256(value: str, name: str) -> None:
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{name} must be a sha256 digest")
