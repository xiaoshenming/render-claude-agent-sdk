"""Small data contracts for post-render logic repair."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


LogicState = Literal[
    "PASS",
    "NEEDS_REPAIR",
    "PATCHED",
    "RENDER_OK",
    "FIXED",
    "ROLLBACK",
    "DEGRADED",
    "HUMAN_REVIEW",
]

IssueSeverity = Literal["low", "medium", "high", "critical"]


@dataclass(slots=True)
class SceneDigest:
    scene_id: str
    line_start: int
    line_end: int
    texts: list[str] = field(default_factory=list)
    formulas: list[str] = field(default_factory=list)
    code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogicEvidence:
    source_code_hash: str
    job_id: str = ""
    problem_text: str = ""
    expected_answer: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    render_meta: dict[str, Any] = field(default_factory=dict)
    scenes: list[SceneDigest] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogicIssue:
    issue_id: str
    issue_type: str
    severity: IssueSeverity
    confidence: float
    repairable: bool
    repair_scope: str
    target_scene_ids: list[str]
    evidence: list[dict[str, Any]]
    expected: str = ""
    observed: str = ""
    acceptance_predicates: list[dict[str, Any]] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewReport:
    review_id: str
    source_code_hash: str
    decision: Literal["pass", "repair", "record_only", "human_review"]
    issues: list[LogicIssue] = field(default_factory=list)
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RepairPlan:
    plan_id: str
    issue_ids: list[str]
    repair_scope: str
    target_scene_ids: list[str]
    allowed_edit_regions: list[dict[str, Any]]
    repair_strategy: str
    forbidden_changes: list[str]
    acceptance_predicates: list[dict[str, Any]]
    max_coder_attempts: int = 1
    fallback: Literal["rollback", "mark_degraded_no_repair", "human_review"] = (
        "mark_degraded_no_repair"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RepairAttempt:
    repair_attempt_id: str
    plan_id: str
    declared_scope: str
    touched_regions: list[dict[str, Any]]
    changed_claims: list[dict[str, Any]]
    patch: dict[str, str] = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecheckReport:
    recheck_id: str
    checked_issue_ids: list[str]
    results: list[dict[str, Any]]
    final_decision: Literal["accept_repair", "reject_repair", "unverifiable"]
    new_issue_scan: Literal["disabled"] = "disabled"
    out_of_scope_observations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogicRunResult:
    state: LogicState
    evidence: LogicEvidence
    review: ReviewReport | None = None
    plan: RepairPlan | None = None
    attempt: RepairAttempt | None = None
    recheck: RecheckReport | None = None
    fixed_code: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
