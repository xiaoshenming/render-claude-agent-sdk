from __future__ import annotations

import json
from pathlib import Path

from manim_quality.agents._runtime_models import CorrectableOutputError
from manim_quality.agents.managed_tools import (
    ManagedToolGrant,
    ToolEffect,
)
from manim_quality.contracts._json_values import thaw_json_object

from .contracts import REQUIRED_TOOLS, validate_assurance_output
from .models import AssuranceCase, ToolReport
from .risk_frames import inspect_risk_frames, multimodal_content
from .tools import (
    inspect_artifact,
    inspect_code_review,
    inspect_consistency,
    inspect_execution,
    inspect_layout,
    inspect_tts,
)

_SCHEMA = {
    "type": "object",
    "properties": {"case_key": {"type": "string"}},
    "required": ["case_key"],
    "additionalProperties": False,
}


class AssuranceToolset:
    def __init__(self, case: AssuranceCase, output_dir: Path) -> None:
        self.case = case
        self.output_dir = output_dir
        self.reports: dict[str, ToolReport] = {}

    def grants(self) -> tuple[ManagedToolGrant, ...]:
        handlers = {
            "inspect_artifact": inspect_artifact,
            "inspect_execution": inspect_execution,
            "inspect_code_review": inspect_code_review,
            "inspect_layout": inspect_layout,
            "inspect_tts": inspect_tts,
            "inspect_consistency": inspect_consistency,
        }
        grants = [
            self._grant(
                name,
                lambda _args, fn=fn, tool_name=name: self._run(tool_name, fn),
            )
            for name, fn in handlers.items()
        ]
        grants.append(
            self._grant("inspect_risk_frames", self._run_risk_frames, chars=80_000)
        )
        return tuple(grants)

    def validate_output(self, value) -> None:
        self._record_output_attempt(value)
        try:
            validate_assurance_output(value)
            missing = REQUIRED_TOOLS - self.reports.keys()
            if missing:
                raise ValueError(f"Agent skipped required tools: {sorted(missing)}")
        except ValueError as error:
            raise CorrectableOutputError(str(error)) from error

    def _record_output_attempt(self, value) -> None:
        path = self.output_dir / "structured-output-attempts.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "output": thaw_json_object(value),
                        "observed_tools": sorted(self.reports),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    def _run(self, name: str, fn):
        report = fn(self.case)
        self.reports[name] = report
        return json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True)

    def _run_risk_frames(self, _arguments):
        report = inspect_risk_frames(self.case, self.output_dir)
        self.reports[report.tool] = report
        return multimodal_content(report)

    def _grant(self, name: str, handler, chars: int = 30_000) -> ManagedToolGrant:
        def checked(arguments):
            if arguments["case_key"] != self.case.key:
                raise ValueError("case_key does not match bound assurance case")
            return handler(arguments)

        return ManagedToolGrant(
            server_name="assurance",
            name=name,
            description=(
                f"Inspect {name.removeprefix('inspect_').replace('_', ' ')} for the "
                "single bound final-delivery case and return immutable evidence."
            ),
            input_schema=_SCHEMA,
            handler=checked,
            effect=ToolEffect.READ_ONLY,
            max_calls=1,
            timeout_ms=180_000,
            max_result_chars=chars,
        )
