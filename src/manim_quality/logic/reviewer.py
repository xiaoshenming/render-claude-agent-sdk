"""Stateless read-only Logic Reviewer built on the shared Agent Runtime."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from manim_quality.agents._runtime_models import (
    AgentRunFailed,
    CorrectableOutputError,
    OutputRejected,
)
from manim_quality.agents.profile import AgentProfile, AgentRole
from manim_quality.agents.runtime import (
    AgentRunRequest,
    AgentRunResult,
    AgentRuntime,
)
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.agents.usage import AgentCallRecord
from manim_quality.geometry.schemas import GeometrySnapshot
from manim_quality.geometry.sdk_tool import geometry_inspector_tool
from manim_quality.revisions.fingerprint import code_hash, evidence_hash

from ._errors import ReviewOutputValidationError
from ._review_output import bind_review_output
from .engine_adapter import verify_engine_review_evidence
from .evidence import LogicEvidence
from .output_schema import REVIEW_OUTPUT_SCHEMA
from .review_input import ReviewInputVersion, build_review_prompt
from .schemas import LogicReviewReport


class LogicReviewError(RuntimeError):
    def __init__(
        self, message: str, *, call_record: AgentCallRecord | None = None
    ) -> None:
        self.call_record = call_record
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LogicReviewResult:
    report: LogicReviewReport
    call_record: AgentCallRecord


class LogicReviewer:
    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        profile: AgentProfile,
        input_version: ReviewInputVersion = ReviewInputVersion.EVIDENCE_V1,
    ) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be AgentRuntime")
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        if profile.role is not AgentRole.REVIEWER:
            raise ValueError("Logic Reviewer requires the read-only reviewer profile")
        if not isinstance(input_version, ReviewInputVersion):
            raise TypeError("input_version must be ReviewInputVersion")
        self._runtime = runtime
        self._profile = profile
        self._input_version = input_version

    def review(
        self,
        *,
        run_id: str,
        evidence: LogicEvidence,
        workspace: Path,
        candidate_path: Path,
        render_manifest_path: Path,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int = 0,
        reserved_cache_write_tokens: int = 0,
        geometry_snapshot: GeometrySnapshot | None = None,
    ) -> LogicReviewResult:
        if not isinstance(evidence, LogicEvidence):
            raise TypeError("evidence must be LogicEvidence")
        candidate, manifest = _load_bound_files(
            evidence, workspace, candidate_path, render_manifest_path
        )
        _verify_engine_binding(evidence, candidate)
        read_tools = _geometry_read_tools(
            self._input_version, geometry_snapshot, evidence.code_hash
        )
        prompt = _versioned_prompt(
            evidence,
            candidate,
            workspace,
            candidate_path,
            render_manifest_path,
            self._input_version,
            geometry_snapshot,
        )
        context_bytes = _context_bytes(prompt, candidate, manifest)
        request = AgentRunRequest(
            run_id=run_id,
            profile=self._profile,
            prompt=prompt,
            output_schema=REVIEW_OUTPUT_SCHEMA,
            workspace=workspace,
            readable_paths=(candidate_path, render_manifest_path),
            editable_paths=(),
            context_bytes=context_bytes,
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=reserved_cache_read_tokens,
            reserved_cache_write_tokens=reserved_cache_write_tokens,
            output_validator=_review_output_validator(
                review_id=run_id,
                evidence=evidence,
                candidate=candidate,
                manifest=manifest.decode("utf-8"),
            ),
            read_tools=read_tools,
            tool_policies=_tool_policies(self._input_version),
        )
        result = _run_with_output_boundary(self._runtime, request)
        report = _bind_result(result, run_id, evidence, candidate, manifest)
        return LogicReviewResult(report=report, call_record=result.record)


def _bind_result(
    result: AgentRunResult,
    run_id: str,
    evidence: LogicEvidence,
    candidate: str,
    manifest: bytes,
) -> LogicReviewReport:
    try:
        return bind_review_output(
            result.structured_output,
            review_id=run_id,
            evidence=evidence,
            candidate_code=candidate,
            render_manifest_text=manifest.decode("utf-8"),
        )
    except ReviewOutputValidationError as error:
        raise LogicReviewError(
            f"invalid Logic Reviewer output: {error}", call_record=result.record
        ) from error


def _versioned_prompt(
    evidence: LogicEvidence,
    candidate: str,
    workspace: Path,
    candidate_path: Path,
    manifest_path: Path,
    input_version: ReviewInputVersion,
    geometry_snapshot: GeometrySnapshot | None,
) -> str:
    root = Path(workspace).resolve()
    return build_review_prompt(
        evidence=evidence,
        candidate_code=candidate,
        candidate_path=Path(candidate_path).resolve().relative_to(root),
        manifest_path=Path(manifest_path).resolve().relative_to(root),
        input_version=input_version,
        geometry_snapshot=geometry_snapshot,
    )


def _geometry_read_tools(
    input_version: ReviewInputVersion,
    snapshot: GeometrySnapshot | None,
    expected_code_hash: str,
):
    geometry_version = input_version is ReviewInputVersion.DIGEST_V2_2_GEOMETRY
    if not geometry_version:
        if snapshot is not None:
            raise ValueError("geometry snapshot requires geometry review input version")
        return ()
    if not isinstance(snapshot, GeometrySnapshot):
        raise ValueError("geometry review requires a geometry snapshot")
    if snapshot.code_hash != expected_code_hash:
        raise ValueError("geometry snapshot does not match candidate code")
    return (geometry_inspector_tool(snapshot),)


def _tool_policies(input_version: ReviewInputVersion):
    if input_version is not ReviewInputVersion.DIGEST_V2_2_GEOMETRY:
        return {}
    return {
        "Read": ToolInputPolicy(
            max_calls=2,
            required_fields=("offset", "limit"),
            integer_minimums={"offset": 1, "limit": 1},
            integer_maximums={"limit": 160},
            clamp_integer_maximums=True,
        )
    }


def _load_bound_files(
    evidence: LogicEvidence,
    workspace: Path,
    candidate_path: Path,
    manifest_path: Path,
) -> tuple[str, bytes]:
    root = Path(workspace).resolve(strict=True)
    candidate = _task_file(root, candidate_path, "candidate_path")
    manifest = _task_file(root, manifest_path, "render_manifest_path")
    try:
        candidate_text = candidate.read_text(encoding="utf-8")
        manifest_bytes = manifest.read_bytes()
    except (OSError, UnicodeError) as error:
        raise LogicReviewError(f"unable to read review artifact: {error}") from error
    if code_hash(candidate_text) != evidence.code_hash:
        raise LogicReviewError("candidate code no longer matches LogicEvidence")
    if evidence_hash(manifest_bytes) != evidence.render_manifest_hash:
        raise LogicReviewError("render manifest no longer matches LogicEvidence")
    try:
        manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LogicReviewError("render manifest must be UTF-8") from error
    return candidate_text, manifest_bytes


def _task_file(root: Path, value: Path, name: str) -> Path:
    try:
        path = Path(value).resolve(strict=True)
    except OSError as error:
        raise LogicReviewError(f"{name} cannot be resolved") from error
    if not path.is_relative_to(root) or not path.is_file():
        raise LogicReviewError(f"{name} must be a file inside the task workspace")
    return path


def _verify_engine_binding(evidence: LogicEvidence, candidate: str) -> None:
    try:
        verify_engine_review_evidence(candidate, evidence.engine_evidence)
    except (TypeError, ValueError) as error:
        raise LogicReviewError(
            f"engine evidence does not match candidate: {error}"
        ) from error


def _context_bytes(prompt: str, candidate: str, manifest: bytes) -> int:
    schema = json.dumps(REVIEW_OUTPUT_SCHEMA, sort_keys=True, separators=(",", ":"))
    return (
        len(prompt.encode("utf-8"))
        + len(candidate.encode("utf-8"))
        + len(manifest)
        + len(schema.encode("utf-8"))
    )


def _review_output_validator(
    *,
    review_id: str,
    evidence: LogicEvidence,
    candidate: str,
    manifest: str,
) -> Callable[[Mapping[str, object]], None]:
    def validate(value: Mapping[str, object]) -> None:
        try:
            bind_review_output(
                value,
                review_id=review_id,
                evidence=evidence,
                candidate_code=candidate,
                render_manifest_text=manifest,
            )
        except ReviewOutputValidationError as error:
            raise CorrectableOutputError(str(error)) from error

    return validate


def _run_with_output_boundary(
    runtime: AgentRuntime, request: AgentRunRequest
) -> AgentRunResult:
    try:
        return runtime.run(request)
    except AgentRunFailed as error:
        if not isinstance(error.__cause__, OutputRejected):
            raise
        raise LogicReviewError(
            f"invalid Logic Reviewer output: {error.__cause__}",
            call_record=error.record,
        ) from error
