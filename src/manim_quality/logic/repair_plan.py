"""Immutable multi-issue repair plans bound to one candidate revision."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._validation import (
    freeze_identifier_sequence,
    freeze_string_sequence,
    require_non_empty_string,
)
from manim_quality.revisions.fingerprint import sha256_text

from ._scene_evidence import SceneDigest
from .schemas import LogicDecision, LogicIssue, LogicReviewReport

_FORBIDDEN_CHANGES = (
    "BaseConfigScene, header, helper, import, or configuration changes",
    "layout or overlap changes",
    "unrelated wording or teaching-method improvements",
    "new solution methods not required by the frozen issues",
    "edits to undeclared Scenes",
)


@dataclass(frozen=True, slots=True)
class EditRegion:
    scene_id: str
    line_start: int
    line_end: int

    def __post_init__(self) -> None:
        require_non_empty_string(self.scene_id, "scene_id")
        if type(self.line_start) is not int or type(self.line_end) is not int:
            raise TypeError("edit region line bounds must be integers")
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError("edit region line bounds are invalid")


@dataclass(frozen=True, slots=True)
class RepairPlan:
    plan_id: str
    source_code_hash: str
    issues: Sequence[LogicIssue]
    target_scene_ids: Sequence[str]
    allowed_edit_regions: Sequence[EditRegion]
    forbidden_changes: Sequence[str]
    max_attempts: int = 2

    def __post_init__(self) -> None:
        require_non_empty_string(self.plan_id, "plan_id")
        require_sha256(self.source_code_hash, "source_code_hash")
        issues = tuple(self.issues)
        if not all(isinstance(issue, LogicIssue) for issue in issues):
            raise TypeError("issues must contain LogicIssue values")
        object.__setattr__(self, "issues", issues)
        scenes = freeze_identifier_sequence(self.target_scene_ids, "target_scene_ids")
        object.__setattr__(self, "target_scene_ids", scenes)
        regions = tuple(self.allowed_edit_regions)
        if not all(isinstance(region, EditRegion) for region in regions):
            raise TypeError("allowed_edit_regions must contain EditRegion values")
        if tuple(region.scene_id for region in regions) != scenes:
            raise ValueError("edit regions must match target Scenes in order")
        object.__setattr__(self, "allowed_edit_regions", regions)
        object.__setattr__(
            self,
            "forbidden_changes",
            freeze_string_sequence(self.forbidden_changes, "forbidden_changes"),
        )
        if isinstance(self.max_attempts, bool) or not isinstance(
            self.max_attempts, int
        ):
            raise TypeError("max_attempts must be an integer")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.max_attempts > 2:
            raise ValueError("logic repair cannot exceed two attempts")

    @property
    def issue_ids(self) -> tuple[str, ...]:
        return tuple(issue.issue_id for issue in self.issues)


def build_repair_plan(
    report: LogicReviewReport, scenes: Sequence[SceneDigest]
) -> RepairPlan:
    if not isinstance(report, LogicReviewReport):
        raise TypeError("report must be LogicReviewReport")
    if report.decision is not LogicDecision.NEEDS_REPAIR:
        raise ValueError("repair plan requires a NEEDS_REPAIR report")
    scene_index = _scene_index(scenes)
    targets = tuple(
        scene_id
        for scene_id in scene_index
        if any(scene_id in issue.target_scene_ids for issue in report.issues)
    )
    unknown = sorted(
        {scene_id for issue in report.issues for scene_id in issue.target_scene_ids}
        - scene_index.keys()
    )
    if unknown:
        raise ValueError(
            f"repair issues reference unknown Scene(s): {', '.join(unknown)}"
        )
    _reject_conflicting_claims(report.issues)
    return RepairPlan(
        plan_id=_plan_id(report, targets),
        source_code_hash=report.code_hash,
        issues=report.issues,
        target_scene_ids=targets,
        allowed_edit_regions=tuple(
            EditRegion(
                scene_id,
                scene_index[scene_id].line_start,
                scene_index[scene_id].line_end,
            )
            for scene_id in targets
        ),
        forbidden_changes=_FORBIDDEN_CHANGES,
    )


def _scene_index(scenes: Sequence[SceneDigest]) -> dict[str, SceneDigest]:
    values = tuple(scenes)
    if not values or not all(isinstance(scene, SceneDigest) for scene in values):
        raise TypeError("scenes must contain SceneDigest values")
    index = {scene.scene_id: scene for scene in values}
    if len(index) != len(values):
        raise ValueError("Scene digest identifiers must be unique")
    return index


def _plan_id(report: LogicReviewReport, targets: Sequence[str]) -> str:
    payload = json.dumps(
        {
            "code_hash": report.code_hash,
            "issue_ids": [issue.issue_id for issue in report.issues],
            "target_scene_ids": list(targets),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"repair-plan-{sha256_text(payload).removeprefix('sha256:')[:16]}"


def _reject_conflicting_claims(issues: Sequence[LogicIssue]) -> None:
    expected_by_evidence: dict[tuple[object, ...], str] = {}
    for issue in issues:
        for citation in issue.evidence:
            if citation.artifact.value != "candidate_code":
                continue
            key = (
                citation.scene_id,
                citation.line_start,
                citation.line_end,
                citation.excerpt,
            )
            expected = " ".join(issue.expected.split()).casefold()
            previous = expected_by_evidence.setdefault(key, expected)
            if previous != expected:
                message = "conflicting expected claims for the same code evidence"
                raise ValueError(message)
