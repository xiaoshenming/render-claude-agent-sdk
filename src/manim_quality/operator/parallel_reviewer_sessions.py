"""Provider-neutral parallel Reviewer sessions."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from manim_quality.agents._reviewer_values import reviewer_payload
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRunRequest
from manim_quality.contracts._json_values import thaw_json_object

from .figure_fidelity import OUTPUT_SCHEMA as FIGURE_OUTPUT_SCHEMA
from .figure_fidelity import _validate_output as validate_figure_output

REVIEWER_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "needs_repair"]},
        "diagnosis": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "target": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "required_invariant": {"type": "string"},
                    "repair_scope": {"type": "string"},
                },
                "required": [
                    "type",
                    "target",
                    "evidence",
                    "required_invariant",
                    "repair_scope",
                ],
                "additionalProperties": False,
            },
        },
        "coverage": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "checked_items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["summary", "checked_items"],
            "additionalProperties": False,
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["decision", "diagnosis", "issues", "coverage", "confidence"],
    "additionalProperties": False,
}


def run_parallel_reviewer_sessions(
    runtime, *, candidate, specs, tools, model: str, effort: str,
):
    by_name = {tool.name: tool for tool in tools}
    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        rows = tuple(pool.map(
            lambda spec: _run_one(runtime, candidate, by_name, model, effort, spec),
            specs,
        ))
    records = tuple(row.pop("_record") for row in rows)
    return rows, records


def _run_one(runtime, candidate, by_name, model, effort, spec):
    grants = tuple(by_name[name.rsplit("__", 1)[-1]] for name in spec.allowed_tools)
    output_schema, schema_version, validator = _output_contract(spec.name)
    request = AgentRunRequest(
        run_id=f"reviewer-{spec.name}-{candidate.parent.name}",
        profile=reviewer_profile(
            model=model,
            prompt_version=f"parallel-{spec.name}-{spec.prompt_version}",
            schema_version=schema_version,
        ),
        prompt=spec.prompt, output_schema=output_schema,
        workspace=candidate.parent, readable_paths=(candidate,), editable_paths=(),
        context_bytes=len(spec.prompt.encode("utf-8")), estimated_input_tokens=400,
        reserved_output_tokens=2_000, reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0, output_validator=validator,
        managed_tools=grants, effort=effort,
    )
    outcome = runtime.run(request)
    raw = thaw_json_object(outcome.structured_output)
    payload = reviewer_payload(json.dumps(raw), ValueError)
    observed = [call for call in outcome.record.tool_calls
                if call.name in spec.allowed_tools and call.allowed]
    raw_text = json.dumps(raw, ensure_ascii=False)
    return {
        "agent_type": spec.name, "agent_id": request.run_id,
        "tool_use_id": request.run_id, "parent_tool_use_id": None,
        "started_ms": None, "stopped_ms": None, "completed_ms": None,
        "is_error": False, "content": raw_text, "raw_content": raw_text,
        "payload": payload, "raw_payload": raw,
        "sdk_metadata": {
            "subagent_tokens": outcome.record.usage.total_tokens,
            "tool_uses": len(observed) if observed else None,
            "duration_ms": outcome.record.elapsed_ms,
        },
        "parent_next_message_id": "parallel-session-complete",
        "_record": outcome.record,
    }


def _output_contract(name: str):
    if name == "figure_fidelity_reviewer":
        return (
            FIGURE_OUTPUT_SCHEMA,
            "figure-fidelity-output-v4",
            validate_figure_output,
        )
    return REVIEWER_SCHEMA, "native-reviewer-result-v1", None
