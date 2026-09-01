"""Parallel native Reviewer sessions over provider-neutral tool calls."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from manim_quality.agents.subagents import NativeSubagentSpec

from .figure_fidelity import (
    locate_confirmed_figure,
)
from .native_reviewer_results import ordered_results
from .parallel_reviewer_sessions import run_parallel_reviewer_sessions
from .reviewer_tools import build_reviewer_tools
from .source_view import extract_solution

PROMPTS = Path(__file__).with_name("prompts")
STANDARD_SPECS = (
    ("math_geometry_reviewer", "math_geometry_reviewer_v1.md", "v3"),
    ("animation_lifecycle_reviewer", "animation_lifecycle_reviewer_v1.md", "v3"),
    ("visual_layout_reviewer", "visual_layout_reviewer_v1.md", "v3"),
)


def run_native_reviewer_group(
    runtime,
    *,
    candidate_path: Path,
    problem_text: str,
    solution_steps: str,
    final_answer: str = "",
    parsed_standard_answer: str = "",
    teaching_script: str = "",
    reviewer_supplemental_notes: dict[str, str] | None = None,
    layout_evidence: dict[str, object] | None = None,
    model: str,
    effort: str,
):
    candidate = candidate_path.resolve(strict=True)
    figure = locate_confirmed_figure(candidate)
    tools = build_reviewer_tools(candidate, figure, layout_evidence or {})
    teaching_script = teaching_script or solution_steps
    parsed_standard_answer = parsed_standard_answer or final_answer
    specs = _specs(
        tools, candidate, figure, problem_text, parsed_standard_answer,
        teaching_script, reviewer_supplemental_notes or {}, effort,
    )
    rows, records = run_parallel_reviewer_sessions(
        runtime, candidate=candidate, specs=specs, tools=tools,
        model=model, effort=effort,
    )
    return ordered_results(rows, specs, model), records


def _specs(
    tools, candidate, figure, problem, parsed_answer, teaching_script,
    notes, effort,
):
    by_name = {item.name: item.sdk_name for item in tools}
    solution_tool = by_name["read_solution"]
    specs = []
    for name, prompt_name, prompt_version in STANDARD_SPECS:
        prompt = _standard_prompt(
            prompt_name, candidate, problem, teaching_script,
            parsed_answer=parsed_answer,
            supplemental_note=str(notes.get(_note_key(name)) or ""),
        )
        allowed = (solution_tool,)
        if name == "visual_layout_reviewer" and "read_layout_evidence" in by_name:
            prompt += (
                "\n\nCall `mcp__quality__read_layout_evidence` exactly once with "
                '`{"revision_id":"R0"}` and audit every returned BBox '
                "candidate."
            )
            allowed += (by_name["read_layout_evidence"],)
        specs.append(NativeSubagentSpec(
            name=name,
            description=f"Run the independent {name} source audit.",
            prompt=prompt,
            allowed_tools=allowed,
            prompt_version=prompt_version,
            max_turns=5,
            effort=effort,
        ))
    if figure is not None:
        specs.append(
            NativeSubagentSpec(
                name="figure_fidelity_reviewer",
                description=(
                    "Compare confirmed figure source with candidate Solution."
                ),
                prompt=_figure_prompt(
                    candidate,
                    supplemental_note=str(
                        notes.get("review4_figure_fidelity") or ""),
                ),
                allowed_tools=(
                    by_name["read_confirmed_figure"],
                    solution_tool,
                ),
                prompt_version="v5",
                max_turns=6,
                effort=effort,
            )
        )
    return tuple(specs)


def _standard_prompt(
    name, candidate, problem, steps="", final_answer="", *,
    parsed_answer="", supplemental_note="",
):
    text = _fill(
        PROMPTS / name, candidate, problem, steps,
        parsed_answer or final_answer, supplemental_note,
    )
    replacement = (
        "1. Call `mcp__quality__read_solution` exactly once with "
        '`{"revision_id":"R0"}`. Audit only the returned Solution and '
        "do not edit.\n2."
    )
    return re.sub(r"1\. Use native `Read`.*?\n2\.", replacement, text, flags=re.S)


def _figure_prompt(candidate, supplemental_note=""):
    text = _fill(
        PROMPTS / "figure_fidelity_reviewer_v4.md",
        candidate,
        "",
        "",
        "",
        supplemental_note,
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


def _fill(
    path, candidate, problem, teaching_script="", parsed_answer="",
    supplemental_note="",
):
    solution = extract_solution(candidate.read_text(encoding="utf-8"))
    line_count = solution.end_line - solution.start_line + 1
    return (
        path.read_text(encoding="utf-8")
        .replace("{{PROBLEM_TEXT}}", problem.strip())
        .replace("{{SOLUTION_STEPS}}", teaching_script.strip())
        .replace("{{TEACHING_SCRIPT}}", teaching_script.strip())
        .replace("{{PARSED_STANDARD_ANSWER}}", parsed_answer.strip())
        .replace("{{FINAL_ANSWER}}", parsed_answer.strip())
        .replace("{{SUPPLEMENTAL_NOTE}}", supplemental_note.strip())
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


def _note_key(name: str) -> str:
    return {
        "math_geometry_reviewer": "review1_math_logic",
        "animation_lifecycle_reviewer": "review2_animation_lifecycle",
        "visual_layout_reviewer": "review3_visual_layout",
    }[name]


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
