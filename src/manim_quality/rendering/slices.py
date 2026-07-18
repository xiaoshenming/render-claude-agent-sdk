"""Immutable Scene slice plans and deterministic render manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from manim_quality.storage import ArtifactRef

from .impact import SourceImpact, scene_order_hash


@dataclass(frozen=True, slots=True)
class CertifiedSlice:
    scene_id: str
    scene_hash: str
    artifact: ArtifactRef
    source_revision_id: str
    source_manifest_hash: str
    certification_hash: str
    render_config_hash: str
    renderer_version: str
    assets_hash: str
    scene_order_hash: str
    shared_dependency_hash: str
    external_dependencies_hash: str
    environment_evidence_hash: str
    environment_version: str

    def __post_init__(self) -> None:
        _require_text(self.scene_id, "scene_id")
        _require_hash(self.scene_hash, "scene_hash")
        if not isinstance(self.artifact, ArtifactRef):
            raise TypeError("artifact must be an ArtifactRef")
        _require_text(self.source_revision_id, "source_revision_id")
        _require_hash(self.source_manifest_hash, "source_manifest_hash")
        _require_hash(self.certification_hash, "certification_hash")
        _require_hash(self.render_config_hash, "render_config_hash")
        _require_text(self.renderer_version, "renderer_version")
        _require_hash(self.assets_hash, "assets_hash")
        _require_hash(self.scene_order_hash, "scene_order_hash")
        _require_hash(self.shared_dependency_hash, "shared_dependency_hash")
        _require_hash(self.external_dependencies_hash, "external_dependencies_hash")
        _require_hash(self.environment_evidence_hash, "environment_evidence_hash")
        _require_text(self.environment_version, "environment_version")


@dataclass(frozen=True, slots=True)
class CandidateSlice:
    scene_id: str
    scene_hash: str
    artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class RenderPlan:
    render_scene_ids: tuple[str, ...]
    reusable_slices: Mapping[str, CertifiedSlice]
    full_rerender: bool
    full_rerender_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "render_scene_ids", tuple(self.render_scene_ids))
        object.__setattr__(
            self,
            "reusable_slices",
            MappingProxyType(dict(self.reusable_slices)),
        )
        object.__setattr__(
            self, "full_rerender_reasons", tuple(self.full_rerender_reasons)
        )


class RenderPlanInput(Protocol):
    ordered_scene_ids: Sequence[str]
    scene_hashes: Mapping[str, str]
    certified_slices: Mapping[str, CertifiedSlice]
    render_config_hash: str
    renderer_version: str
    assets_hash: str


class EnvironmentInput(Protocol):
    assets_hash: str
    external_dependencies_hash: str
    complete: bool
    uncertain: bool
    evidence_hash: str
    version: str


def build_render_plan(
    request: RenderPlanInput,
    impact: SourceImpact,
    environment: EnvironmentInput,
) -> RenderPlan:
    reasons = _full_rerender_reasons(request, impact, environment)
    full = bool(reasons)
    reusable: dict[str, CertifiedSlice] = {}
    render: list[str] = []
    for scene_id in request.ordered_scene_ids:
        certified = request.certified_slices.get(scene_id)
        can_reuse = (
            not full
            and certified is not None
            and certified.scene_hash == impact.scene_hashes[scene_id]
            and _environment_matches(request, environment, certified)
        )
        if can_reuse:
            reusable[scene_id] = certified
        else:
            render.append(scene_id)
    return RenderPlan(tuple(render), reusable, full, reasons)


def restrict_reuse(
    plan: RenderPlan,
    ordered_scene_ids: Sequence[str],
    authorized_scene_ids: set[str],
) -> RenderPlan:
    reusable = {
        scene_id: item
        for scene_id, item in plan.reusable_slices.items()
        if scene_id in authorized_scene_ids
    }
    render = tuple(
        scene_id for scene_id in ordered_scene_ids if scene_id not in reusable
    )
    return RenderPlan(render, reusable, plan.full_rerender, plan.full_rerender_reasons)


def _environment_matches(
    request: RenderPlanInput,
    environment: EnvironmentInput,
    certified: CertifiedSlice,
) -> bool:
    return (
        environment.complete
        and not environment.uncertain
        and certified.render_config_hash == request.render_config_hash
        and certified.renderer_version == request.renderer_version
        and certified.assets_hash == environment.assets_hash
        and certified.external_dependencies_hash
        == environment.external_dependencies_hash
        and certified.environment_evidence_hash == environment.evidence_hash
        and certified.environment_version == environment.version
        and certified.scene_order_hash == scene_order_hash(request.ordered_scene_ids)
    )


def _full_rerender_reasons(
    request: RenderPlanInput,
    impact: SourceImpact,
    environment: EnvironmentInput,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if not environment.complete or environment.uncertain:
        reasons.add("environment_uncertain")
    order_hash = scene_order_hash(request.ordered_scene_ids)
    for item in request.certified_slices.values():
        checks = (
            (
                item.shared_dependency_hash != impact.shared_dependency_hash,
                "shared_dependency_changed",
            ),
            (
                item.render_config_hash != request.render_config_hash,
                "render_config_changed",
            ),
            (item.renderer_version != request.renderer_version, "renderer_changed"),
            (item.assets_hash != environment.assets_hash, "assets_changed"),
            (
                item.external_dependencies_hash
                != environment.external_dependencies_hash,
                "external_dependencies_changed",
            ),
            (
                item.environment_evidence_hash != environment.evidence_hash,
                "environment_evidence_changed",
            ),
            (
                item.environment_version != environment.version,
                "environment_version_changed",
            ),
            (item.scene_order_hash != order_hash, "scene_order_changed"),
        )
        reasons.update(reason for mismatch, reason in checks if mismatch)
    return tuple(sorted(reasons))


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_hash(value: object, name: str) -> str:
    text = _require_text(value, name)
    if not text.startswith("sha256:") or len(text) != 71:
        raise ValueError(f"{name} must be a sha256 hash")
    return text
