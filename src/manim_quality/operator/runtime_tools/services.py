"""Shared real render/BBox toolchain and protocol adapters."""

from __future__ import annotations

import json
import threading
from itertools import count
from pathlib import Path

import anyio

from manim_quality.operator.models import CandidateAttempt, Finding, ValidationOutcome

from .detector import LayoutIssueDetector
from .issues import compact_layout_report
from .layout_diff import compare_layout_reports
from .models import ProbeResult, RenderResult
from .probe import BBoxProbe
from .render import ManimRenderer
from .workspace import RevisionWorkspace


class RuntimeToolchain:
    def __init__(
        self,
        *,
        source_workspace: Path,
        artifact_root: Path,
        probe_runner: Path,
        python_executable: Path,
        environment: dict[str, str] | None = None,
        detector_path: Path | None = None,
        scene_name: str = "Solution",
    ) -> None:
        self._workspaces = RevisionWorkspace(artifact_root)
        self.reports_dir = Path(artifact_root) / "reports"
        self._renderer = ManimRenderer(
            source_workspace=source_workspace,
            python_executable=python_executable,
            environment=environment,
            scene_name=scene_name,
        )
        self._probe = BBoxProbe(
            source_workspace=source_workspace,
            runner_path=probe_runner,
            python_executable=python_executable,
            environment=environment,
            scene_name=scene_name,
        )
        detector_path = detector_path or (
            Path(__file__).resolve().parents[4]
            / ".vendor"
            / "quality_repair"
            / "tools"
            / "quality_repair_checkers"
            / "layout_probe_check.py"
        )
        self._detector = LayoutIssueDetector(detector_path)
        self._renders: dict[str, RenderResult] = {}
        self._probes: dict[str, ProbeResult] = {}
        # Tools may run concurrently in worker threads within one round;
        # the reentrant lock serializes render/probe so the same revision
        # is never rendered twice and workspace writes never race.
        self._lock = threading.RLock()

    def render(self, revision: CandidateAttempt) -> RenderResult:
        with self._lock:
            return self._render_locked(revision)

    def _render_locked(self, revision: CandidateAttempt) -> RenderResult:
        cached = self._renders.get(revision.code_hash)
        if cached is not None:
            return cached
        revision_dir, candidate = self._workspaces.materialize(revision)
        result = self._renderer.render(revision_dir, candidate)
        self._renders[revision.code_hash] = result
        return result

    def probe(self, revision: CandidateAttempt) -> ProbeResult:
        with self._lock:
            return self._probe_locked(revision)

    def _probe_locked(self, revision: CandidateAttempt) -> ProbeResult:
        cached = self._probes.get(revision.code_hash)
        if cached is not None:
            return cached
        rendered = self._render_locked(revision)
        if not rendered.ok:
            result = ProbeResult(
                False,
                rendered.revision_dir / "bbox_probe.json",
                {},
                "render_required_before_bbox_probe",
            )
        else:
            result = self._probe.inspect(
                rendered.revision_dir,
                rendered.candidate_path,
            )
        self._probes[revision.code_hash] = result
        return result

    def layout_report(self, revision: CandidateAttempt) -> dict[str, object]:
        result = self.probe(revision)
        if not result.ok:
            return {
                "blocking_count": 1,
                "returned_issue_count": 1,
                "truncated": False,
                "issues": [
                    {
                        "issue_id": "layout-probe-failed",
                        "category": "layout_probe_failure",
                        "objects": [],
                        "acceptance_criteria": "Real render and BBox probe complete.",
                    }
                ],
            }
        detector_payload = self._detector.detect(
            result.payload,
            artifact_path=result.raw_path.with_name("layout_detector.json"),
        )
        return compact_layout_report(detector_payload)


def _persist_report(
    toolchain: RuntimeToolchain,
    kind: str,
    revision_id: str,
    sequence: count,
    payload: dict[str, object],
) -> None:
    """Persist each in-session verification fact the moment it exists.

    Session death (timeout, protocol failure, SIGKILL) must never erase
    already-computed render or layout evidence.
    """

    directory = toolchain.reports_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{kind}.{revision_id}.{next(sequence):02d}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class RealRevisionValidator:
    def __init__(self, toolchain: RuntimeToolchain) -> None:
        self._toolchain = toolchain
        self._sequence = count(1)

    async def validate(
        self,
        revision: CandidateAttempt,
        findings: tuple[Finding, ...],
        problem_hash: str,
    ) -> ValidationOutcome:
        del findings
        result = await anyio.to_thread.run_sync(
            self._toolchain.render,
            revision,
            abandon_on_cancel=True,
        )
        details = {
            "compiled": result.ok,
            "rendered": result.ok,
            "video_path": str(result.video_path) if result.video_path else None,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
        }
        _persist_report(
            self._toolchain,
            "validation",
            revision.revision_id,
            self._sequence,
            {
                "revision_id": revision.revision_id,
                "code_hash": revision.code_hash,
                "problem_hash": problem_hash,
                **details,
            },
        )
        return ValidationOutcome(
            passed=result.ok,
            improved=result.ok,
            summary=(
                "real Manim render passed"
                if result.ok
                else "real Manim render failed"
            ),
            details=details,
            revision_id=revision.revision_id,
            code_hash=revision.code_hash,
            problem_hash=problem_hash,
        )


class RealLayoutInspector:
    def __init__(self, toolchain: RuntimeToolchain) -> None:
        self._toolchain = toolchain
        self._baselines: dict[str, dict[str, object]] = {}
        self._sequence = count(1)

    async def inspect(
        self,
        revision: CandidateAttempt,
        problem_hash: str,
    ) -> dict[str, object]:
        def _probe_and_report():
            probe = self._toolchain.probe(revision)
            return probe, self._toolchain.layout_report(revision)

        result, compact = await anyio.to_thread.run_sync(
            _probe_and_report,
            abandon_on_cancel=True,
        )
        report = {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "verified": result.ok,
            "error": result.error,
            **compact,
        }
        if revision.revision_id == "R0" and problem_hash not in self._baselines:
            self._baselines[problem_hash] = dict(report)
        baseline = self._baselines.get(problem_hash)
        if baseline is not None:
            report["comparison_to_R0"] = compare_layout_reports(baseline, report)
        _persist_report(
            self._toolchain,
            "layout",
            revision.revision_id,
            self._sequence,
            report,
        )
        return report
