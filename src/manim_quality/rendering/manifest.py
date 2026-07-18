"""Canonical content and provenance manifests for candidate renders."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.storage import ArtifactRef

from .slices import CandidateSlice, RenderPlan


@dataclass(frozen=True, slots=True)
class ManifestSlice:
    scene_id: str
    scene_hash: str
    artifact: ArtifactRef
    reused: bool
    source_revision_id: str | None = None
    source_manifest_hash: str | None = None
    certification_hash: str | None = None

    def evidence_dict(self) -> dict[str, object]:
        provenance = None
        if self.reused:
            provenance = {
                "certification_hash": self.certification_hash,
                "source_manifest_hash": self.source_manifest_hash,
                "source_revision_id": self.source_revision_id,
            }
        return {
            **self.content_dict(),
            "reuse_provenance": provenance,
            "reused": self.reused,
        }

    def content_dict(self) -> dict[str, object]:
        return {
            "artifact_hash": self.artifact.hash,
            "media_type": self.artifact.media_type,
            "scene_hash": self.scene_hash,
            "scene_id": self.scene_id,
            "size": self.artifact.size,
        }


@dataclass(frozen=True, slots=True)
class RenderManifest:
    revision_id: str
    code_hash: str
    render_config_hash: str
    renderer_version: str
    assets_hash: str
    external_dependencies_hash: str
    environment_evidence_hash: str
    environment_version: str
    environment_complete: bool
    environment_uncertain: bool
    slices: tuple[ManifestSlice, ...]
    final_video: ArtifactRef

    def content_canonical_bytes(self) -> bytes:
        return _canonical_json(
            {
                "assets_hash": self.assets_hash,
                "code_hash": self.code_hash,
                "external_dependencies_hash": self.external_dependencies_hash,
                "final_video": _artifact_dict(self.final_video),
                "render_config_hash": self.render_config_hash,
                "renderer_version": self.renderer_version,
                "schema_version": 1,
                "slices": [item.content_dict() for item in self.slices],
            }
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_json(
            {
                "content_hash": self.content_hash,
                "environment_complete": self.environment_complete,
                "environment_evidence_hash": self.environment_evidence_hash,
                "environment_uncertain": self.environment_uncertain,
                "environment_version": self.environment_version,
                "revision_id": self.revision_id,
                "schema_version": 1,
                "slices": [item.evidence_dict() for item in self.slices],
            }
        )

    @property
    def content_hash(self) -> str:
        return sha256_bytes(self.content_canonical_bytes())

    @property
    def evidence_hash(self) -> str:
        return sha256_bytes(self.canonical_bytes())

    @property
    def hash(self) -> str:
        return self.evidence_hash


class ManifestRequest(Protocol):
    revision_id: str
    code_hash: str
    render_config_hash: str
    renderer_version: str
    ordered_scene_ids: Sequence[str]


class ManifestEnvironment(Protocol):
    assets_hash: str
    external_dependencies_hash: str
    evidence_hash: str
    version: str
    complete: bool
    uncertain: bool


def ordered_manifest_slices(
    request: ManifestRequest,
    plan: RenderPlan,
    rendered: Mapping[str, CandidateSlice],
) -> tuple[ManifestSlice, ...]:
    result = []
    for scene_id in request.ordered_scene_ids:
        reused = scene_id in plan.reusable_slices
        item = plan.reusable_slices[scene_id] if reused else rendered[scene_id]
        provenance = _reuse_provenance(item) if reused else (None, None, None)
        result.append(
            ManifestSlice(scene_id, item.scene_hash, item.artifact, reused, *provenance)
        )
    return tuple(result)


def build_manifest(
    request: ManifestRequest,
    slices: tuple[ManifestSlice, ...],
    final_video: ArtifactRef,
    environment: ManifestEnvironment,
) -> RenderManifest:
    return RenderManifest(
        request.revision_id,
        request.code_hash,
        request.render_config_hash,
        request.renderer_version,
        environment.assets_hash,
        environment.external_dependencies_hash,
        environment.evidence_hash,
        environment.version,
        environment.complete,
        environment.uncertain,
        slices,
        final_video,
    )


def _reuse_provenance(item: object) -> tuple[str, str, str]:
    return (
        item.source_revision_id,
        item.source_manifest_hash,
        item.certification_hash,
    )


def _artifact_dict(artifact: ArtifactRef) -> dict[str, object]:
    return {
        "artifact_hash": artifact.hash,
        "media_type": artifact.media_type,
        "size": artifact.size,
    }


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
