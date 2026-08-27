"""Provider-neutral parallel Reviewer sessions."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from manim_quality.agents._reviewer_values import reviewer_payload
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRunRequest
from manim_quality.contracts._json_values import thaw_json_object

REVIEWER_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "needs_repair"]},
        "diagnosis": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "object"}},
        "coverage": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["decision", "diagnosis", "issues", "coverage", "confidence"],
    "additionalProperties": True,
}


def run_parallel_reviewer_sessions(
    runtime, *, candidate, specs, tools, model: str, effort: str,
):
    by_name = {tool.name: tool for tool in tools}

    def run_one(spec):
        grants = tuple(
            by_name[name.rsplit("__", 1)[-1]] for name in spec.allowed_tools
        )
        request = AgentRunRequest(
            run_id=f"reviewer-{spec.name}-{candidate.parent.name}",
            profile=reviewer_profile(
                model=model,
                prompt_version=f"parallel-{spec.name}-v1",
                schema_version="native-reviewer-result-v1",
            ),
            prompt=spec.prompt,
            output_schema=REVIEWER_SCHEMA,
            workspace=candidate.parent,
            readable_paths=(candidate,),
            editable_paths=(),
            context_bytes=len(spec.prompt.encode("utf-8")),
            estimated_input_tokens=400,
            reserved_output_tokens=2_000,
            reserved_cache_read_tokens=0,
            reserved_cache_write_tokens=0,
            managed_tools=grants,
            effort=effort,
        )
        outcome = runtime.run(request)
        raw = thaw_json_object(outcome.structured_output)
        payload = reviewer_payload(json.dumps(raw), ValueError)
        observed_tools = [
            call for call in outcome.record.tool_calls
            if call.name in spec.allowed_tools and call.allowed
        ]
        return {
            "agent_type": spec.name,
            "agent_id": request.run_id,
            "tool_use_id": request.run_id,
            "parent_tool_use_id": None,
            "started_ms": None,
            "stopped_ms": None,
            "completed_ms": None,
            "is_error": False,
            "content": json.dumps(raw, ensure_ascii=False),
            "raw_content": json.dumps(raw, ensure_ascii=False),
            "payload": payload,
            "raw_payload": raw,
            "sdk_metadata": {
                "subagent_tokens": outcome.record.usage.total_tokens,
                "tool_uses": len(observed_tools) if observed_tools else None,
                "duration_ms": outcome.record.elapsed_ms,
            },
            "parent_next_message_id": "parallel-session-complete",
            "_record": outcome.record,
        }

    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        rows = tuple(pool.map(run_one, specs))
    records = tuple(row.pop("_record") for row in rows)
    return rows, records
