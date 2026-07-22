"""Platform-owned overlap residual-risk and semantic-scope policy."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from manim_quality.revisions import sha256_text

from .geometry_projection import normalize_unframed_translations
from .runtime_policy import OVERLAP_MAX_ROUNDS

_LAYOUT_METHODS = frozenset(
    {
        "align_to",
        "arrange",
        "arrange_in_grid",
        "center",
        "fit_to_canvas",
        "move_to",
        "next_to",
        "scale",
        "scale_to_fit_height",
        "scale_to_fit_width",
        "set_height",
        "set_width",
        "set_x",
        "set_y",
        "set_z",
        "shift",
        "to_corner",
        "to_edge",
    }
)

OBSERVATION_ONLY_TOKEN_CAP = 2**63 - 1


def agent_token_cap(remaining_tokens: int) -> int:
    """Record usage without rejecting a candidate by the platform token estimate."""
    del remaining_tokens
    return OBSERVATION_ONLY_TOKEN_CAP


@dataclass(frozen=True, slots=True)
class ResidualRiskPolicy:
    max_degraded_blocking: int = 2
    min_reduction_ratio: float = 0.5
    full_candidate_min_blocking: int = 4
    full_candidate_min_tokens: int = 20_000
    second_attempt_min_tokens: int = 60_000

    def __post_init__(self) -> None:
        counts = (
            self.max_degraded_blocking,
            self.full_candidate_min_blocking,
            self.full_candidate_min_tokens,
            self.second_attempt_min_tokens,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("overlap policy counts must be non-negative integers")
        if not 0 <= self.min_reduction_ratio <= 1:
            raise ValueError("min_reduction_ratio must be between zero and one")

    def accepts_degraded(self, *, before: int, after: int) -> bool:
        if before <= 0 or after < 0 or after > self.max_degraded_blocking:
            return False
        return (before - after) / before >= self.min_reduction_ratio

    def allow_full_candidate_fallback(
        self,
        *,
        residual_blocking: int,
        stop_reasons: tuple[str, ...],
        remaining_tokens: int,
        attempts_used: int,
    ) -> bool:
        return (
            0 <= attempts_used < OVERLAP_MAX_ROUNDS
            and residual_blocking >= self.full_candidate_min_blocking
            and remaining_tokens >= self.full_candidate_min_tokens
            and "runner_error_no_edit" in stop_reasons
        )

    def allow_core_followup(
        self,
        *,
        before_blocking: int,
        residual_blocking: int,
        remaining_tokens: int,
        attempts_used: int,
    ) -> bool:
        return (
            0 <= attempts_used < OVERLAP_MAX_ROUNDS
            and before_blocking > residual_blocking > self.max_degraded_blocking
            and remaining_tokens >= self.second_attempt_min_tokens
        )


def layout_invariant_fingerprint(source: str) -> str:
    """Hash code semantics after removing only recognized placement calls."""
    tree = ast.parse(source)
    projected = _LayoutProjection().visit(tree)
    projected = normalize_unframed_translations(projected)
    ast.fix_missing_locations(projected)
    canonical = ast.dump(projected, annotate_fields=True, include_attributes=False)
    return sha256_text(canonical)


class _LayoutProjection(ast.NodeTransformer):
    def visit_If(self, node: ast.If) -> ast.AST | None:  # noqa: N802
        if _is_dimension_layout_guard(node):
            return None
        return self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> ast.AST | None:  # noqa: N802
        if _is_layout_call(node.value):
            return None
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        if _is_layout_call(node):
            return self.visit(node.func.value)
        return self.generic_visit(node)


def _is_layout_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LAYOUT_METHODS
        and not _has_nested_call_arguments(node)
    )


def _has_nested_call_arguments(node: ast.Call) -> bool:
    values = (*node.args, *(keyword.value for keyword in node.keywords))
    return any(
        isinstance(item, ast.Call) for value in values for item in ast.walk(value)
    )


def _is_dimension_layout_guard(node: ast.If) -> bool:
    if node.orelse or not node.body or not _is_dimension_test(node.test):
        return False
    return all(
        isinstance(statement, ast.Expr) and _is_layout_call(statement.value)
        for statement in node.body
    )


def _is_dimension_test(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return False
    operands = (node.left, *node.comparators)
    dimensions = [
        item
        for item in operands
        if isinstance(item, ast.Attribute) and item.attr in {"height", "width"}
    ]
    constants = [
        item
        for item in operands
        if isinstance(item, ast.Constant) and type(item.value) in {int, float}
    ]
    return len(dimensions) == 1 and len(constants) == 1
