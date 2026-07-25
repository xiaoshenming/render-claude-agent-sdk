"""Pure evaluation helpers for the expected/actual relation probe."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from manim_quality.logic.expectations.comparison import (
    ComparisonStatus,
    RelationComparison,
    compare_expected_relations,
)
from manim_quality.logic.expectations.schemas import ExpectedRelationContract
from manim_quality.logic.expectations.symbolic_index import build_symbolic_index


@dataclass(frozen=True, slots=True)
class CodeEvaluation:
    flagged: bool
    target_hit: bool | None
    counts: dict[str, int]
    comparisons: tuple[RelationComparison, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "flagged": self.flagged,
            "target_hit": self.target_hit,
            "counts": dict(self.counts),
            "comparisons": [_comparison_dict(item) for item in self.comparisons],
        }


def evaluate_code(
    code: str,
    scene_id: str,
    contract: ExpectedRelationContract,
    *,
    target_line: int | None = None,
) -> CodeEvaluation:
    index = build_symbolic_index(code, scene_id=scene_id)
    comparisons = compare_expected_relations(contract, index)
    contradictions = tuple(
        item
        for item in comparisons
        if item.status is ComparisonStatus.CONTRADICTION
    )
    counts = {status.value: 0 for status in ComparisonStatus}
    for item in comparisons:
        counts[item.status.value] += 1
    target_hit = None
    if target_line is not None:
        target_hit = any(target_line in item.candidate_lines for item in contradictions)
    return CodeEvaluation(bool(contradictions), target_hit, counts, comparisons)


def resolve_scene_id(meta: Mapping[str, object], code: str) -> str:
    scenes = _scene_classes(code)
    declared = meta.get("scene_name")
    if isinstance(declared, str) and declared.strip() in scenes:
        return declared.strip()
    for preferred in ("Solution", "MainScene"):
        if preferred in scenes:
            return preferred
    if len(scenes) == 1:
        return scenes[0]
    raise ValueError("candidate Scene cannot be resolved unambiguously")


def _scene_classes(code: str) -> tuple[str, ...]:
    tree = ast.parse(code)
    return tuple(
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(item, ast.FunctionDef) and item.name == "construct"
            for item in node.body
        )
    )


def _comparison_dict(item: RelationComparison) -> dict[str, object]:
    claim = item.claim
    return {
        "claim_id": claim.claim_id,
        "relation": claim.relation,
        "operands": list(claim.operands),
        "source_kind": claim.source_kind,
        "evidence": claim.evidence,
        "confidence": claim.confidence,
        "status": item.status.value,
        "actual": dict(item.actual),
        "reason_code": item.reason_code,
        "candidate_lines": list(item.candidate_lines),
    }
