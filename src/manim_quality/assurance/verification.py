from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.operator.reviewers import build_reviewer_specs
from manim_quality.operator.runtime_tools import (
    RealLayoutInspector,
    RealRevisionValidator,
    RuntimeToolchain,
    geometry_sidecar_runner,
)
from manim_quality.operator.services import BasicRelationChecker
from manim_quality.operator.session import QualitySession
from manim_quality.operator.toolset import build_quality_tools

from .models import AssuranceCase, ToolReport


@dataclass(frozen=True, slots=True)
class VerificationConfig:
    manim_python: Path
    runtime_python_paths: tuple[Path, ...]


class AssuranceVerification:
    def __init__(
        self,
        case: AssuranceCase,
        output_dir: Path,
        config: VerificationConfig,
    ) -> None:
        if case.source_path is None or not case.source_path.is_file():
            raise ValueError("final source is required for full assurance")
        source = case.source_path.read_text(encoding="utf-8")
        self.case = case
        self.session = QualitySession(
            problem_text=case.question or f"case:{case.key}",
            candidate_code=source,
        )
        environment = _render_environment(case, config)
        repo = Path(__file__).resolve().parents[3]
        toolchain = RuntimeToolchain(
            source_workspace=case.source_path.parent,
            artifact_root=output_dir / "fresh-runtime",
            probe_runner=Path(geometry_sidecar_runner.__file__),
            python_executable=config.manim_python,
            environment=environment,
        )
        self.layout = RealLayoutInspector(toolchain)
        self.validator = RealRevisionValidator(toolchain)
        all_tools = build_quality_tools(
            session=self.session,
            relation_checker=BasicRelationChecker(),
            layout_inspector=self.layout,
            revision_validator=self.validator,
        )
        self.reviewer_tools = tuple(
            replace(tool, max_calls=12) if tool.name == "check_relation" else tool
            for tool in all_tools
            if tool.name in {"read_solution", "check_relation"}
        )
        self.reviewers = build_reviewer_specs(self.reviewer_tools, effort="low")
        self.repo = repo

    async def inspect_render(self) -> ToolReport:
        revision = self.session.baseline
        outcome = await self.validator.validate(
            revision,
            (),
            self.session.problem_hash,
        )
        evidence = {
            "id": f"{self.case.key}:fresh-render",
            "revision_id": outcome.revision_id,
            "local_revision_alias": "R0",
            "delivery_revision_id": self.case.delivery_revision_id,
            "code_hash": outcome.code_hash,
            "problem_hash": outcome.problem_hash,
            "passed": outcome.passed,
            "summary": outcome.summary,
            "details": thaw_json_object(outcome.details),
        }
        risks = () if outcome.passed else ("fresh_render_failed",)
        return ToolReport(
            "inspect_execution",
            "complete" if outcome.passed else "risk",
            risks,
            (evidence,),
        )

    async def inspect_layout(self) -> ToolReport:
        revision = self.session.baseline
        report = await self.layout.inspect(revision, self.session.problem_hash)
        blocking = int(report.get("blocking_count") or 0)
        risks = ("fresh_bbox_blocking",) if blocking else ()
        status = (
            "risk"
            if risks
            else ("complete" if report.get("verified") else "incomplete")
        )
        return ToolReport(
            "inspect_layout",
            status,
            risks,
            ({"id": f"{self.case.key}:fresh-layout", **report},),
        )


def _render_environment(
    case: AssuranceCase,
    config: VerificationConfig,
) -> dict[str, str]:
    roots = [_silent_shim(), *config.runtime_python_paths]
    environment = {"PYTHONPATH": os.pathsep.join(str(path) for path in roots)}
    assets = case.source_path.parent / "assets"
    if assets.is_dir():
        environment["MATHPI_RENDER_ASSETS_DIR"] = str(assets)
    environment["MANIM_LAYOUT_PROBE_DELEGATE"] = str(
        Path(__file__).resolve().parents[3] / "vendor/layout_probe/probe_runner.txt"
    )
    return environment


def _silent_shim() -> Path:
    root = Path(__file__).resolve().parents[3]
    vendor = root / "vendor/logic_engine_mvp_baseline/tools/logic_engine_mvp"
    sys.path.insert(0, str(vendor))
    try:
        from logic_engine_mvp.render_check import _ensure_tts_shim_dir

        return _ensure_tts_shim_dir()
    finally:
        sys.path.remove(str(vendor))
