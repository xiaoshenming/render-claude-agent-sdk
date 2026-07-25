"""Typed command boundary and immutable candidate-render evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from manim_quality.revisions.fingerprint import sha256_text
from manim_quality.storage import ArtifactRef

from .manifest import RenderManifest
from .slices import (
    CandidateSlice,
    CertifiedSlice,
    RenderPlan,
    _require_hash,
    _require_text,
)


class RenderFailureStage(StrEnum):
    SOURCE_VALIDATION = "source_validation"
    IMPACT_ANALYSIS = "impact_analysis"
    CERTIFICATION = "certification"
    ENVIRONMENT = "environment"
    REUSE_VALIDATION = "reuse_validation"
    COMPILE = "compile"
    SCENE_RENDER = "scene_render"
    CONCATENATE = "concatenate"


@dataclass(frozen=True, slots=True)
class RenderRequest:
    revision_id: str
    source_code: str
    code_hash: str
    scene_hashes: Mapping[str, str]
    ordered_scene_ids: Sequence[str]
    certified_slices: Mapping[str, CertifiedSlice]
    render_config_hash: str
    renderer_version: str
    assets_hash: str

    def __post_init__(self) -> None:
        _require_text(self.revision_id, "revision_id")
        _require_text(self.source_code, "source_code")
        _require_hash(self.code_hash, "code_hash")
        if sha256_text(self.source_code) != self.code_hash:
            raise ValueError("source_code does not match code_hash")
        _require_hash(self.render_config_hash, "render_config_hash")
        _require_hash(self.assets_hash, "assets_hash")
        _require_text(self.renderer_version, "renderer_version")
        scenes = _freeze_ids(
            self.ordered_scene_ids, "ordered_scene_ids", allow_empty=False
        )
        hashes = _freeze_hashes(self.scene_hashes)
        certified = _freeze_certified(self.certified_slices)
        if set(hashes) != set(scenes):
            raise ValueError("scene_hashes must exactly match ordered_scene_ids")
        if not set(certified).issubset(scenes):
            raise ValueError("certified_slices contain an unknown Scene")
        object.__setattr__(self, "ordered_scene_ids", scenes)
        object.__setattr__(self, "scene_hashes", hashes)
        object.__setattr__(self, "certified_slices", certified)


@dataclass(frozen=True, slots=True)
class EnvironmentEvidence:
    assets_hash: str
    external_dependencies_hash: str
    complete: bool
    uncertain: bool
    evidence_hash: str
    version: str

    def __post_init__(self) -> None:
        _require_hash(self.assets_hash, "assets_hash")
        _require_hash(self.external_dependencies_hash, "external_dependencies_hash")
        if type(self.complete) is not bool or type(self.uncertain) is not bool:
            raise TypeError("complete and uncertain must be bool")
        _require_hash(self.evidence_hash, "evidence_hash")
        _require_text(self.version, "version")


@dataclass(frozen=True, slots=True)
class CommandResult:
    succeeded: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    succeeded: bool
    artifact: ArtifactRef | None
    message: str = ""

    @classmethod
    def success(cls, artifact: ArtifactRef) -> ArtifactResult:
        return cls(True, artifact)

    @classmethod
    def failure(cls, message: str) -> ArtifactResult:
        return cls(False, None, message)


@runtime_checkable
class Renderer(Protocol):
    def compile(self, request: RenderRequest) -> CommandResult: ...

    def render_scene(self, request: RenderRequest, scene_id: str) -> ArtifactResult: ...

    def concatenate(
        self, request: RenderRequest, slices: tuple[ArtifactRef, ...]
    ) -> ArtifactResult: ...


@runtime_checkable
class CertificationAuthority(Protocol):
    def authorize_reuse(self, item: CertifiedSlice) -> bool: ...


@runtime_checkable
class EnvironmentAuthority(Protocol):
    def resolve_environment(self, request: RenderRequest) -> EnvironmentEvidence: ...


@dataclass(frozen=True, slots=True)
class RenderEvidence:
    succeeded: bool
    plan: RenderPlan
    manifest: RenderManifest | None = None
    failure_stage: RenderFailureStage | None = None
    failure_message: str = ""
    rendered_slices: tuple[CandidateSlice, ...] = ()


def _freeze_ids(
    value: Sequence[str], name: str, *, allow_empty: bool
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence")
    result = tuple(_require_text(item, name) for item in value)
    if (not allow_empty and not result) or len(set(result)) != len(result):
        raise ValueError(f"{name} must be unique and satisfy its cardinality")
    return result


def _freeze_hashes(
    value: Mapping[str, str], *, field_name: str = "scene_hashes"
) -> Mapping[str, str]:
    frozen = {_require_text(key, field_name): item for key, item in value.items()}
    for key, item in frozen.items():
        _require_hash(item, f"{field_name}[{key}]")
    return MappingProxyType(dict(frozen))


def _freeze_certified(
    value: Mapping[str, CertifiedSlice],
) -> Mapping[str, CertifiedSlice]:
    frozen = dict(value)
    for key, item in frozen.items():
        if not isinstance(item, CertifiedSlice) or key != item.scene_id:
            raise ValueError("certified_slices keys must match CertifiedSlice.scene_id")
    return MappingProxyType(frozen)
