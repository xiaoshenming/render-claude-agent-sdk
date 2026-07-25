"""Read-only Agent adapter for extracting explicit expected relations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents._runtime_models import AgentRunRequest
from manim_quality.agents.profile import AgentProfile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import AgentCallRecord

from .schemas import (
    ExpectedRelationContract,
    expected_relation_output_schema,
    parse_expected_relation_contract,
)


@dataclass(frozen=True, slots=True)
class ExpectedRelationExtraction:
    contract: ExpectedRelationContract
    call_record: AgentCallRecord


class ExpectedRelationExtractor:
    def __init__(self, *, runtime: AgentRuntime, profile: AgentProfile) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be AgentRuntime")
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        self._runtime = runtime
        self._profile = profile

    def build_prompt(self, source_path: Path) -> str:
        path = Path(source_path).resolve()
        return f"""You extract explicit mathematical geometry relations.

Read exactly this source file once:
{path}

The file may contain a problem, a reference solution, and a video plan.
Return only relations explicitly stated or directly derived in that material.
Every claim needs a short verbatim source quote. Use source_kind problem,
solution, or plan. Use confidence explicit for a direct statement and derived
only for an immediate definition-level consequence.

Supported relations and operand order:
- line_endpoints: [segment, point1, point2]
- point_on_line: [point, segment]
- parallel: [segment1, segment2]
- perpendicular: [segment1, segment2]
- collinear: [point1, point2, point3]
- equal_length: [segment1, segment2]
- midpoint: [midpoint, endpoint1, endpoint2]
- point_coordinate: [point, x, y, z]
- segment_length: [segment, length]
- intersection: [point, segment1, segment2]

Represent a segment by its endpoint letters, for example AD or BC. When the
material explicitly says to connect, draw, extend, or construct a named
segment, emit line_endpoints as well as any stated relation. Split a statement
with more than three collinear points into supported three-point claims.

Do not diagnose candidate errors or suggest code edits. Do not infer from
standard diagram conventions alone. Omit uncertain claims. An empty claims
array is valid.
"""

    def extract(
        self,
        *,
        run_id: str,
        workspace: Path,
        source_path: Path,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
    ) -> ExpectedRelationExtraction:
        root = Path(workspace).resolve(strict=True)
        source = Path(source_path).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("source_path must be a file inside workspace")
        prompt = self.build_prompt(source)
        request = AgentRunRequest(
            run_id=run_id,
            profile=self._profile,
            prompt=prompt,
            output_schema=expected_relation_output_schema(),
            workspace=root,
            readable_paths=(source,),
            editable_paths=(),
            context_bytes=len(prompt.encode("utf-8")) + source.stat().st_size,
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=estimated_input_tokens,
            reserved_cache_write_tokens=estimated_input_tokens,
            output_validator=parse_expected_relation_contract,
        )
        result = self._runtime.run(request)
        contract = parse_expected_relation_contract(result.structured_output)
        return ExpectedRelationExtraction(contract, result.record)
