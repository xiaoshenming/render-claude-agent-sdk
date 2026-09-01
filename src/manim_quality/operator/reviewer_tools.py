"""Read-only tools shared by native Reviewer sessions."""

from __future__ import annotations

import json
from pathlib import Path

from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect

from .source_view import extract_solution


def build_reviewer_tools(
    candidate: Path,
    figure: Path | None,
    layout_evidence: dict[str, object],
) -> tuple[ManagedToolGrant, ...]:
    tools = [_solution_tool(candidate)]
    if layout_evidence:
        tools.append(_layout_tool(layout_evidence))
    if figure is not None:
        tools.append(_figure_tool(figure))
    return tuple(tools)


def _solution_tool(candidate: Path) -> ManagedToolGrant:
    solution = extract_solution(candidate.read_text(encoding="utf-8"))

    async def read_solution(_arguments):
        return json.dumps({
            "source": solution.source,
            "start_line": solution.start_line,
            "end_line": solution.end_line,
            "sha256": solution.sha256,
        }, ensure_ascii=False)

    return _grant(
        "read_solution", "Read the immutable candidate Solution.",
        read_solution, max_calls=4,
    )


def _layout_tool(layout_evidence: dict[str, object]) -> ManagedToolGrant:
    async def read_layout(_arguments):
        return json.dumps({
            key: layout_evidence.get(key)
            for key in (
                "verified", "blocking_count", "issues",
                "agent_bbox_candidates", "probe_summary", "capture_mode",
            )
            if key in layout_evidence
        }, ensure_ascii=False)

    return _grant(
        "read_layout_evidence",
        "Read raw BBox candidates from the same immutable render.",
        read_layout, max_calls=1,
    )


def _figure_tool(figure: Path) -> ManagedToolGrant:
    async def read_figure(_arguments):
        return json.dumps({
            "source": figure.read_text(encoding="utf-8"),
            "figure_plan": _figure_plan(figure),
        }, ensure_ascii=False)

    return _grant(
        "read_confirmed_figure", "Read the immutable confirmed figure.",
        read_figure, max_calls=1,
    )


def _grant(name, description, handler, *, max_calls):
    return ManagedToolGrant(
        server_name="quality",
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {"revision_id": {"type": "string", "enum": ["R0"]}},
            "required": ["revision_id"],
            "additionalProperties": False,
        },
        handler=handler,
        effect=ToolEffect.READ_ONLY,
        max_calls=max_calls,
        timeout_ms=10_000,
        max_result_chars=80_000,
    )


def _figure_plan(figure: Path) -> str:
    try:
        value = json.loads(
            figure.with_name("figure-plan.json").read_text(encoding="utf-8")
        )
        return json.dumps(value, ensure_ascii=False)[:12_000]
    except (OSError, ValueError, TypeError):
        return '{"visual_role":"unknown"}'
