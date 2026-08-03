"""Build the bounded native Read/Edit request for one Quality Operator."""

from __future__ import annotations

from manim_quality.agents.runtime import AgentRunRequest
from manim_quality.agents.tool_policy import ToolInputPolicy

from .candidate_io import live_solution_read
from .output_schema import OPERATOR_OUTPUT_SCHEMA
from .toolset import build_quality_tools


def operator_request(
    *,
    run_id,
    profile,
    prompt,
    workspace,
    candidate_path,
    session,
    relation_checker,
    layout_inspector,
    revision_validator,
    context_bytes,
    output_validator,
    estimated_input_tokens,
    reserved_output_tokens,
    reserved_cache_read_tokens,
    reserved_cache_write_tokens,
):
    tools = build_quality_tools(
        session=session,
        relation_checker=relation_checker,
        layout_inspector=layout_inspector,
        revision_validator=revision_validator,
        candidate_path=candidate_path,
    )
    return AgentRunRequest(
        run_id=run_id,
        profile=profile,
        prompt=prompt,
        output_schema=OPERATOR_OUTPUT_SCHEMA,
        workspace=workspace,
        readable_paths=(candidate_path,),
        editable_paths=(candidate_path,),
        context_bytes=context_bytes,
        estimated_input_tokens=estimated_input_tokens,
        reserved_output_tokens=reserved_output_tokens,
        reserved_cache_read_tokens=reserved_cache_read_tokens,
        reserved_cache_write_tokens=reserved_cache_write_tokens,
        output_validator=output_validator,
        managed_tools=tools,
        tool_policies={
            "Read": ToolInputPolicy(
                max_calls=120,
                required_fields=("offset", "limit"),
                input_normalizer=live_solution_read(
                    candidate_path,
                    on_read=lambda: session.mark_solution_read(
                        session.current_revision.revision_id
                    ),
                ),
            )
        },
        subagents=(),
        effort="low",
    )
