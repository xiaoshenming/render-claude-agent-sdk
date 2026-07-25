"""Fail-closed compile, targeted Scene render, and concatenation adapter."""

from __future__ import annotations

from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.storage import ArtifactRef, ArtifactStore

from .interfaces import (
    ArtifactResult,
    CertificationAuthority,
    CommandResult,
    EnvironmentAuthority,
    EnvironmentEvidence,
    Renderer,
    RenderEvidence,
    RenderFailureStage,
    RenderRequest,
)
from .manifest import build_manifest, ordered_manifest_slices
from .slices import CandidateSlice, RenderPlan
from .validation import prepare_render


class ManimRenderAdapter:
    """Produce render evidence without repository or promotion authority."""

    def __init__(
        self,
        renderer: Renderer,
        artifact_store: ArtifactStore,
        certification_authority: CertificationAuthority,
        environment_authority: EnvironmentAuthority,
    ) -> None:
        if not isinstance(renderer, Renderer):
            raise TypeError("renderer must implement Renderer")
        if not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must implement ArtifactStore")
        if not isinstance(certification_authority, CertificationAuthority):
            raise TypeError("certification_authority must implement its protocol")
        if not isinstance(environment_authority, EnvironmentAuthority):
            raise TypeError("environment_authority must implement its protocol")
        self._renderer = renderer
        self._artifacts = artifact_store
        self._authority = certification_authority
        self._environment = environment_authority

    def render(self, request: RenderRequest) -> RenderEvidence:
        preparation = prepare_render(request, self._environment, self._authority)
        plan = preparation.plan
        if preparation.failure_stage is not None:
            return _failure(plan, preparation.failure_stage, preparation.failure_detail)
        environment = preparation.environment
        if environment is None:
            return _failure(
                plan, RenderFailureStage.ENVIRONMENT, "environment evidence missing"
            )
        invalid_reuse = self._invalid_reuse(plan)
        if invalid_reuse is not None:
            return _failure(plan, RenderFailureStage.REUSE_VALIDATION, invalid_reuse)
        try:
            compiled = self._renderer.compile(request)
        except Exception as error:
            return _failure(plan, RenderFailureStage.COMPILE, error)
        if not _valid_command_result(compiled):
            return _failure(plan, RenderFailureStage.COMPILE, "invalid compile result")
        if not compiled.succeeded:
            return _failure(plan, RenderFailureStage.COMPILE, compiled.message)
        rendered, failure = self._render_required(request, plan)
        if failure is not None:
            return failure
        return self._concatenate(request, plan, rendered, environment)

    def _concatenate(
        self,
        request: RenderRequest,
        plan: RenderPlan,
        rendered: dict[str, CandidateSlice],
        environment: EnvironmentEvidence,
    ) -> RenderEvidence:
        ordered = ordered_manifest_slices(request, plan, rendered)
        try:
            concatenated = self._renderer.concatenate(
                request, tuple(item.artifact for item in ordered)
            )
        except Exception as error:
            return _failure(
                plan, RenderFailureStage.CONCATENATE, error, tuple(rendered.values())
            )
        if not _valid_artifact_result(concatenated):
            return _failure(
                plan,
                RenderFailureStage.CONCATENATE,
                "invalid concatenate result",
                tuple(rendered.values()),
            )
        if not concatenated.succeeded:
            return _failure(
                plan,
                RenderFailureStage.CONCATENATE,
                concatenated.message,
                tuple(rendered.values()),
            )
        if not self._artifact_matches(concatenated.artifact):
            return _failure(
                plan,
                RenderFailureStage.CONCATENATE,
                "concatenated artifact is corrupt",
                tuple(rendered.values()),
            )
        manifest = build_manifest(request, ordered, concatenated.artifact, environment)
        return RenderEvidence(
            True, plan, manifest, rendered_slices=tuple(rendered.values())
        )

    def _invalid_reuse(self, plan: RenderPlan) -> str | None:
        for scene_id, item in plan.reusable_slices.items():
            if not self._artifact_matches(item.artifact):
                return f"{scene_id}: certified slice artifact is corrupt"
        return None

    def _render_required(
        self, request: RenderRequest, plan: RenderPlan
    ) -> tuple[dict[str, CandidateSlice], RenderEvidence | None]:
        rendered: dict[str, CandidateSlice] = {}
        for scene_id in plan.render_scene_ids:
            try:
                result = self._renderer.render_scene(request, scene_id)
            except Exception as error:
                return rendered, _failure(
                    plan,
                    RenderFailureStage.SCENE_RENDER,
                    error,
                    tuple(rendered.values()),
                )
            if not _valid_artifact_result(result):
                return rendered, _failure(
                    plan,
                    RenderFailureStage.SCENE_RENDER,
                    f"{scene_id}: invalid render result",
                    tuple(rendered.values()),
                )
            if not result.succeeded:
                return rendered, _failure(
                    plan,
                    RenderFailureStage.SCENE_RENDER,
                    f"{scene_id}: {result.message}",
                    tuple(rendered.values()),
                )
            if not self._artifact_matches(result.artifact):
                return rendered, _failure(
                    plan,
                    RenderFailureStage.SCENE_RENDER,
                    f"{scene_id}: rendered artifact is corrupt",
                    tuple(rendered.values()),
                )
            rendered[scene_id] = CandidateSlice(
                scene_id, request.scene_hashes[scene_id], result.artifact
            )
        return rendered, None

    def _artifact_matches(self, artifact: ArtifactRef) -> bool:
        try:
            content = self._artifacts.get(artifact)
        except Exception:
            return False
        return len(content) == artifact.size and sha256_bytes(content) == artifact.hash


def _valid_artifact_result(result: object) -> bool:
    if not isinstance(result, ArtifactResult):
        return False
    if type(result.succeeded) is not bool or not isinstance(result.message, str):
        return False
    expected_artifact = isinstance(result.artifact, ArtifactRef)
    return expected_artifact if result.succeeded else result.artifact is None


def _valid_command_result(result: object) -> bool:
    return (
        isinstance(result, CommandResult)
        and type(result.succeeded) is bool
        and isinstance(result.message, str)
    )


def _failure(
    plan: RenderPlan,
    stage: RenderFailureStage,
    detail: object,
    rendered: tuple[CandidateSlice, ...] = (),
) -> RenderEvidence:
    message = detail if isinstance(detail, str) else type(detail).__name__
    return RenderEvidence(
        False,
        plan,
        failure_stage=stage,
        failure_message=message,
        rendered_slices=rendered,
    )
