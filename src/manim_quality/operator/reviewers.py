"""Native foreground Reviewer definitions for the Quality Operator."""

from __future__ import annotations

from pathlib import Path

from manim_quality.agents.managed_tools import ManagedToolGrant
from manim_quality.agents.subagents import NativeSubagentSpec

_PROMPTS = Path(__file__).with_name("prompts")
_READ_TOOL = "read_solution"
_RELATION_TOOL = "check_relation"


def build_reviewer_specs(
    tools: tuple[ManagedToolGrant, ...],
    *,
    effort: str = "low",
) -> tuple[NativeSubagentSpec, ...]:
    by_name = {item.name: item.sdk_name for item in tools}
    allowed = tuple(by_name[name] for name in (_READ_TOOL, _RELATION_TOOL))
    return (
        NativeSubagentSpec(
            name="math_geometry_reviewer",
            description=(
                "Audit all mathematical claims, constructions, coordinates, "
                "labels, and geometric invariants in the current Solution."
            ),
            prompt=_prompt("math_geometry_reviewer_v1.md"),
            allowed_tools=allowed,
            max_turns=5,
            effort=effort,
        ),
        NativeSubagentSpec(
            name="animation_lifecycle_reviewer",
            description=(
                "Audit animation phases, transformed anchors, object ownership, "
                "updaters, and lifecycle consistency in the current Solution."
            ),
            prompt=_prompt("animation_lifecycle_reviewer_v1.md"),
            allowed_tools=allowed,
            max_turns=5,
            effort=effort,
        ),
    )


def _prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()
