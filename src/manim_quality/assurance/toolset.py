from __future__ import annotations

import json
from inspect import isawaitable
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
)
from .tts import inspect_tts
from .verification import AssuranceVerification

_SCHEMA = {
    "type": "object",
    "properties": {"case_key": {"type": "string"}},
    "required": ["case_key"],
    "additionalProperties": False,
}


class AssuranceToolset:
    def __init__(
        self,
        case: AssuranceCase,
        output_dir: Path,
        verification: AssuranceVerification | None = None,
    ) -> None:
        self.case = case
        self.output_dir = output_dir
        self.reports: dict[str, ToolReport] = {}
        self.verification = verification

    def grants(self) -> tuple[ManagedToolGrant, ...]:
        handlers = {
            "inspect_artifact": inspect_artifact,
            "inspect_execution": (
                inspect_execution
                if self.verification is None
                else lambda _case: self.verification.inspect_render()
            ),
            "inspect_code_review": inspect_code_review,
            "inspect_layout": (
                inspect_layout
                if self.verification is None
                else lambda _case: self.verification.inspect_layout()
            ),
            "inspect_tts": inspect_tts,
            "inspect_consistency": inspect_consistency,
        }
        grants = [
            self._grant(
                name,
                lambda _args, fn=fn, tool_name=name: self._run(tool_name, fn),
                timeout_ms=(
                    2_700_000
                    if name in {"inspect_execution", "inspect_layout"}
                    else 180_000
                ),
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
            missing = REQUIRED_TOOLS - self.reports.keys()
            if missing:
                raise ValueError(f"Agent skipped required tools: {sorted(missing)}")
            validate_assurance_output(
                value,
                expected_reports={
                    name: report.as_dict() for name, report in self.reports.items()
                },
            )
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

    async def _run(self, name: str, fn):
        report = fn(self.case)
        if hasattr(report, "__await__"):
            report = await report
        self.reports[name] = report
        return json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True)

    def _run_risk_frames(self, _arguments):
        report = inspect_risk_frames(self.case, self.output_dir)
        self.reports[report.tool] = report
        return multimodal_content(report)

    def _grant(
        self,
        name: str,
        handler,
        chars: int = 30_000,
        timeout_ms: int = 180_000,
    ) -> ManagedToolGrant:
        async def checked(arguments):
            if arguments["case_key"] != self.case.key:
                raise ValueError("case_key does not match bound assurance case")
            result = handler(arguments)
            return await result if isawaitable(result) else result

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
            timeout_ms=timeout_ms,
            max_result_chars=chars,
        )
