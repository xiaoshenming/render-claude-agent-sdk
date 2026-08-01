"""Native foreground Reviewer definitions for the Quality Operator."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.operator.source_view import extract_solution

_PROMPTS = Path(__file__).with_name("prompts")
REVIEWER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "needs_repair"]},
        "diagnosis": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "object"}},
        "coverage": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["decision", "diagnosis", "issues", "coverage", "confidence"],
    "additionalProperties": False,
}


def run_reviewers(
    runtime: AgentRuntime,
    *,
    candidate_path: Path,
    model: str,
    effort: str = "low",
) -> tuple[tuple[dict[str, object], ...], tuple[object, ...]]:
    results = []
    records = []
    for name, prompt_name in (
        ("math_geometry_reviewer", "math_geometry_reviewer_v1.md"),
        ("animation_lifecycle_reviewer", "animation_lifecycle_reviewer_v1.md"),
    ):
        outcome = runtime.run(
            _reviewer_request(
                name, prompt_name, candidate_path, model, effort
            )
        )
        if not any(
            item.allowed and item.name == "Read"
            for item in outcome.record.tool_calls
        ):
            raise RuntimeError(f"{name} did not read the candidate with native Read")
        results.append(
            {
                "agent_type": name,
                "is_error": False,
                "payload": thaw_json_object(outcome.structured_output),
                "usage": (
                    asdict(outcome.record.usage)
                    if outcome.record.usage.total_tokens else None
                ),
                "usage_complete": outcome.record.usage_complete,
                "model": outcome.record.model,
                "duration_ms": outcome.record.elapsed_ms,
                "turns": outcome.record.turns,
                "tool_calls": [
                    item.name for item in outcome.record.tool_calls
                ],
            }
        )
        records.append(outcome.record)
    return tuple(results), tuple(records)


def _reviewer_request(name, prompt_name, candidate_path, model, effort):
    prompt = _prompt(prompt_name, candidate_path)
    start_line, _end_line, line_count = _solution_range(candidate_path)
    exact_read = ToolInputPolicy(
        max_calls=1,
        required_fields=("offset", "limit"),
        integer_minimums={"offset": start_line, "limit": line_count},
        integer_maximums={"offset": start_line, "limit": line_count},
    )
    return AgentRunRequest(
        run_id=f"{name}-{candidate_path.parent.name}",
        profile=reviewer_profile(
            model=model,
            prompt_version=f"{name}-native-read-v1",
            schema_version="quality-reviewer-output-v1",
        ),
        prompt=prompt,
        output_schema=REVIEWER_OUTPUT_SCHEMA,
        workspace=candidate_path.parent,
        readable_paths=(candidate_path,),
        editable_paths=(),
        context_bytes=len(prompt.encode("utf-8")),
        estimated_input_tokens=100,
        reserved_output_tokens=100,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
        tool_policies={"Read": exact_read},
        effort=effort,
    )


def _prompt(name: str, candidate_path: Path) -> str:
    start_line, end_line, line_count = _solution_range(candidate_path)
    return (
        (_PROMPTS / name)
        .read_text(encoding="utf-8")
        .replace("{{CANDIDATE_PATH}}", str(candidate_path))
        .replace("{{SOLUTION_START_LINE}}", str(start_line))
        .replace("{{SOLUTION_END_LINE}}", str(end_line))
        .replace("{{SOLUTION_LINE_COUNT}}", str(line_count))
        .strip()
    )


def _solution_range(candidate_path: Path) -> tuple[int, int, int]:
    solution = extract_solution(candidate_path.read_text(encoding="utf-8"))
    return (
        solution.start_line,
        solution.end_line,
        solution.end_line - solution.start_line + 1,
    )
