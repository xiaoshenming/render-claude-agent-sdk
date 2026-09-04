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
from .identity import ArtifactIdentityReceipt, inspect_artifact_identity
from .models import AssuranceCase, ToolReport
from .output_projection import project_output
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
        self.identity = inspect_artifact_identity(case)

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
        return tuple(grants)

    def validate_output(self, value) -> None:
        try:
            missing = REQUIRED_TOOLS - self.reports.keys()
            if missing:
                raise ValueError(f"Agent skipped required tools: {sorted(missing)}")
            validate_assurance_output(
                self.normalize_output(value),
                expected_reports={
                    name: report.as_dict() for name, report in self.reports.items()
                },
            )
        except ValueError as error:
            self._record_output_attempt(value, str(error))
            raise CorrectableOutputError(str(error)) from error
        self._record_output_attempt(value)

    def normalize_output(self, value) -> dict[str, object]:
        """Bind mechanical receipt fields to immutable observed tool reports."""
        payload = project_output(value, self.reports)
        raw = thaw_json_object(value)
        if raw != payload:
            path = self.output_dir / "output-projections.jsonl"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(
                    {"raw": raw, "projected": payload}, ensure_ascii=False) + "\n")
        return payload

    def _record_output_attempt(self, value, error=None) -> None:
        path = self.output_dir / "structured-output-attempts.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "output": thaw_json_object(value),
                        "observed_tools": sorted(self.reports),
                        "validation_error": error,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

    async def _run(self, name: str, fn):
        cached = self.reports.get(name)
        if cached is not None:
            return json.dumps(cached.as_dict(), ensure_ascii=False, sort_keys=True)
        report = fn(self.case)
        if hasattr(report, "__await__"):
            report = await report
        if name == "inspect_consistency":
            report = _with_identity(report, self.identity)
        self.reports[name] = report
        return json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True)

    def _grant(
        self,
        name: str,
        handler,
        chars: int = 30_000,
        timeout_ms: int = 180_000,
    ) -> ManagedToolGrant:
        async def checked(_arguments):
            # The capability is already bound to exactly one immutable case.  The
            # model-authored case_key is only a protocol echo and must never be
            # allowed to redirect the read or abort the whole assurance run.
            result = handler(_arguments)
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
            # OpenAI-compatible relays may repeat an identical tool request
            # once after receiving its result. These capabilities are
            # deterministic and read-only, so tolerate one bounded replay.
            max_calls=2,
            timeout_ms=timeout_ms,
            max_result_chars=chars,
        )


def _with_identity(
    report: ToolReport,
    identity: ArtifactIdentityReceipt,
) -> ToolReport:
    risks = tuple(dict.fromkeys((*report.risk_codes, *identity.risk_codes)))
    evidence = (*report.evidence, {"id": "artifact-identity", **identity.as_dict()})
    return ToolReport(
        tool=report.tool,
        status="risk" if risks else report.status,
        risk_codes=risks,
        evidence=evidence,
        artifacts=report.artifacts,
    )
