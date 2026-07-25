"""Complete immutable render identity used by final certification."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ._model_validation import require_hash, require_text
from .revision_models import BoundRevision


@dataclass(frozen=True, slots=True)
class RenderBinding:
    revision_id: str
    code_hash: str
    render_manifest_hash: str
    manifest_evidence_hash: str
    manifest_content_hash: str
    final_video_hash: str
    ordered_scene_ids: tuple[str, ...]
    scene_hashes: Mapping[str, str]
    slice_hashes: Mapping[str, str]
    assets_hash: str
    external_dependencies_hash: str
    render_config_hash: str
    renderer_version: str
    environment_version: str
    environment_evidence_hash: str
    environment_complete: bool
    environment_uncertain: bool

    def __post_init__(self) -> None:
        require_text(self.revision_id, "revision_id")
        for name in (
            "code_hash",
            "render_manifest_hash",
            "manifest_evidence_hash",
            "manifest_content_hash",
            "final_video_hash",
            "assets_hash",
            "external_dependencies_hash",
            "render_config_hash",
            "environment_evidence_hash",
        ):
            require_hash(getattr(self, name), name)
        object.__setattr__(self, "ordered_scene_ids", tuple(self.ordered_scene_ids))
        if not self.ordered_scene_ids or len(set(self.ordered_scene_ids)) != len(
            self.ordered_scene_ids
        ):
            raise ValueError("ordered_scene_ids must be non-empty and unique")
        object.__setattr__(
            self, "scene_hashes", MappingProxyType(dict(self.scene_hashes))
        )
        object.__setattr__(
            self, "slice_hashes", MappingProxyType(dict(self.slice_hashes))
        )
        if (
            tuple(self.scene_hashes) != self.ordered_scene_ids
            or tuple(self.slice_hashes) != self.ordered_scene_ids
        ):
            raise ValueError("Scene and slice hashes must match ordered_scene_ids")
        for scene_id, scene_hash in self.scene_hashes.items():
            require_text(scene_id, "scene_id")
            require_hash(scene_hash, f"scene_hashes[{scene_id}]")
            require_hash(self.slice_hashes[scene_id], f"slice_hashes[{scene_id}]")
        require_text(self.renderer_version, "renderer_version")
        require_text(self.environment_version, "environment_version")
        if any(
            type(value) is not bool
            for value in (self.environment_complete, self.environment_uncertain)
        ):
            raise TypeError("environment flags must be bool")


@dataclass(frozen=True, slots=True)
class RenderedCandidate:
    revision: BoundRevision
    render: RenderBinding
