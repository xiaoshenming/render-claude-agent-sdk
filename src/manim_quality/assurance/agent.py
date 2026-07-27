from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents.profile import assurance_profile
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.contracts._json_values import thaw_json_object

from .contracts import ASSURANCE_OUTPUT_SCHEMA
from .models import AssuranceCase
from .toolset import AssuranceToolset

PROMPT = Path(__file__).with_name("prompt.md")


@dataclass(frozen=True, slots=True)
class FinalAssuranceResult:
    output: dict[str, object]
    reports: dict[str, object]
    call_record: object


class FinalAssuranceAgent:
    def __init__(self, runtime: AgentRuntime, model: str) -> None:
        self.runtime = runtime
        self.profile = assurance_profile(
            model=model,
            prompt_version="final-assurance-demo-v1",
            schema_version="final-assurance-output-v1",
            tool_version="final-assurance-tools-v1",
        )

    def run(
        self,
        case: AssuranceCase,
        output_dir: Path,
        *,
        estimated_input_tokens: int = 18_000,
        reserved_output_tokens: int = 4_000,
    ) -> FinalAssuranceResult:
        tools = AssuranceToolset(case, output_dir)
        prompt = PROMPT.read_text(encoding="utf-8") + (
            f"\n\ncase_key: {case.key}\n题目：{case.question}\n"
        )
        request = AgentRunRequest(
            run_id=f"assurance-{case.key}",
            profile=self.profile,
            prompt=prompt,
            output_schema=ASSURANCE_OUTPUT_SCHEMA,
            workspace=output_dir,
            readable_paths=(),
            editable_paths=(),
            context_bytes=len(prompt.encode()) + len(json.dumps(
                ASSURANCE_OUTPUT_SCHEMA).encode()),
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=40_000,
            reserved_cache_write_tokens=0,
            output_validator=tools.validate_output,
            managed_tools=tools.grants(),
            effort="low",
        )
        result = self.runtime.run(request)
        return FinalAssuranceResult(
            output=thaw_json_object(result.structured_output),
            reports={name: report.as_dict() for name, report in tools.reports.items()},
            call_record=result.record,
        )
