"""Parallel native Reviewer sessions over provider-neutral tool calls."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect
from manim_quality.agents.subagents import NativeSubagentSpec

from .figure_fidelity import (
    locate_confirmed_figure,
)
from .native_reviewer_results import ordered_results
from .parallel_reviewer_sessions import run_parallel_reviewer_sessions
from .source_view import extract_solution

PROMPTS = Path(__file__).with_name("prompts")
STANDARD_SPECS = (
    ("math_geometry_reviewer", "math_geometry_reviewer_v1.md"),
    ("animation_lifecycle_reviewer", "animation_lifecycle_reviewer_v1.md"),
    ("visual_layout_reviewer", "visual_layout_reviewer_v1.md"),
)
def run_native_reviewer_group(
    runtime,
    *,
    candidate_path: Path,
    problem_text: str,
    solution_steps: str,
    model: str,
    effort: str,
):
    candidate = candidate_path.resolve(strict=True)
    figure = locate_confirmed_figure(candidate)
    tools = _tools(candidate, figure)
    specs = _specs(tools, candidate, figure, problem_text, solution_steps, effort)
    rows, records = run_parallel_reviewer_sessions(
        runtime, candidate=candidate, specs=specs, tools=tools,
        model=model, effort=effort,
    )
    return ordered_results(rows, specs, model), records


def _tools(candidate: Path, figure: Path | None):
    solution = extract_solution(candidate.read_text(encoding="utf-8"))

    async def read_solution(_arguments):
        return json.dumps(
            {
                "source": solution.source,
                "start_line": solution.start_line,
                "end_line": solution.end_line,
                "sha256": solution.sha256,
            },
            ensure_ascii=False,
        )

    tools = [
        _grant(
            "read_solution",
            "Read the immutable candidate Solution.",
            read_solution,
            max_calls=4,
        )
    ]
    if figure is not None:

        async def read_figure(_arguments):
            return json.dumps(
                {
                    "source": figure.read_text(encoding="utf-8"),
                    "figure_plan": _figure_plan(figure),
                },
                ensure_ascii=False,
            )

        tools.append(
            _grant(
                "read_confirmed_figure",
                "Read the immutable confirmed figure.",
                read_figure,
                max_calls=1,
            )
        )
    return tuple(tools)


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


def _specs(tools, candidate, figure, problem, steps, effort):
    by_name = {item.name: item.sdk_name for item in tools}
    solution_tool = by_name["read_solution"]
    specs = [
        NativeSubagentSpec(
            name=name,
            description=f"Run the independent {name} source audit.",
            prompt=_standard_prompt(prompt_name, candidate, problem, steps),
            allowed_tools=(solution_tool,),
            max_turns=5,
            effort=effort,
        )
        for name, prompt_name in STANDARD_SPECS
    ]
    if figure is not None:
        specs.append(
            NativeSubagentSpec(
                name="figure_fidelity_reviewer",
                description=(
                    "Compare confirmed figure source with candidate Solution."
                ),
                prompt=_figure_prompt(candidate, problem, steps),
                allowed_tools=(
                    by_name["read_confirmed_figure"],
                    solution_tool,
                ),
                max_turns=6,
                effort=effort,
            )
        )
    return tuple(specs)


def _standard_prompt(name, candidate, problem, steps):
    text = _fill(PROMPTS / name, candidate, problem, steps)
    replacement = (
        "1. Call `mcp__quality__read_solution` exactly once with "
        '`{"revision_id":"R0"}`. Audit only the returned Solution and '
        "do not edit.\n2."
    )
    return re.sub(r"1\. Use native `Read`.*?\n2\.", replacement, text, flags=re.S)


def _figure_prompt(candidate, problem, steps):
    text = _fill(
        PROMPTS / "figure_fidelity_reviewer_v4.md",
        candidate,
        problem,
        steps,
    )
    replacement = (
        "必须分别调用 `mcp__quality__read_confirmed_figure` 和 "
        "`mcp__quality__read_solution` 一次，参数均为 "
        '`{"revision_id":"R0"}`。\n\n题图计划：'
    )
    return re.sub(
        r"必须按顺序调用原生 `Read` 两次：.*?题图计划：",
        replacement,
        text,
        flags=re.S,
    )


def _fill(path, candidate, problem, steps):
    solution = extract_solution(candidate.read_text(encoding="utf-8"))
    line_count = solution.end_line - solution.start_line + 1
    return (
        path.read_text(encoding="utf-8")
        .replace("{{PROBLEM_TEXT}}", problem.strip())
        .replace("{{SOLUTION_STEPS}}", steps.strip())
        .replace("{{CONTENT_LANGUAGE}}", _content_language(candidate))
        .replace("{{CANDIDATE_PATH}}", "mcp__quality__read_solution")
        .replace("{{SOLUTION_START_LINE}}", str(solution.start_line))
        .replace("{{SOLUTION_END_LINE}}", str(solution.end_line))
        .replace("{{SOLUTION_LINE_COUNT}}", str(line_count))
        .replace("{{FIGURE_PATH}}", "mcp__quality__read_confirmed_figure")
        .replace("{{FIGURE_LINE_COUNT}}", "managed")
        .replace(
            "{{FIGURE_PLAN}}",
            _figure_plan(locate_confirmed_figure(candidate)),
        )
        .strip()
    )


def _parent_prompt(names):
    return (
        "Call every registered Reviewer exactly once in the foreground, all in "
        f"one assistant turn so they run in parallel: {', '.join(names)}. Use "
        "each exact subagent_type and run_in_background=false. These Reviewers "
        "are read-only MCP agents: use isolation=remote and never request a "
        "worktree. "
        "Wait for every ToolResult, then return only structured output with "
        "status complete."
    )


def _content_language(candidate):
    tree = ast.parse(candidate.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "BATCHOPS_CONTENT_LANGUAGE"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return "zh-CN"


def _figure_plan(figure):
    if figure is None:
        return '{"visual_role":"unknown"}'
    try:
        value = json.loads(
            figure.with_name("figure-plan.json").read_text(encoding="utf-8")
        )
        return json.dumps(value, ensure_ascii=False)[:12_000]
    except (OSError, ValueError, TypeError):
        return '{"visual_role":"unknown"}'
