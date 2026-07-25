"""Immutable revision and evidence identity contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ._formats import require_optional_sha256, require_sha256
from ._validation import (
    freeze_identifier_sequence,
    freeze_string_mapping,
    require_enum,
    require_non_empty_string,
    require_non_negative_int,
    require_optional_string,
    require_wire_array,
    require_wire_object,
    validate_contract_dict,
)

REVISION_SCHEMA_VERSION = 1


class RevisionStage(StrEnum):
    BASELINE = "BASELINE"
    RENDER_REPAIR = "RENDER_REPAIR"
    LOGIC_REPAIR = "LOGIC_REPAIR"
    LAYOUT_REPAIR = "LAYOUT_REPAIR"
    USER_MODIFICATION = "USER_MODIFICATION"


class PatchScope(StrEnum):
    FULL_CANDIDATE = "full_candidate"
    SCENE_LOGIC = "scene_logic"
    LAYOUT_ONLY = "layout_only"
    USER_SCENES = "user_scenes"


class RevisionCreator(StrEnum):
    SYSTEM = "system"
    GENERATION_ADAPTER = "generation_adapter"
    LOGIC_AGENT = "logic_agent"
    OVERLAP_AGENT = "overlap_agent"
    USER = "user"


_FIELDS = frozenset(
    {
        "schema_version",
        "revision_id",
        "parent_revision_id",
        "stage",
        "code_hash",
        "semantic_fingerprint",
        "scene_hashes",
        "render_manifest_hash",
        "changed_scene_ids",
        "patch_scope",
        "created_by",
        "attempt",
    }
)


@dataclass(frozen=True, slots=True)
class Revision:
    revision_id: str
    parent_revision_id: str | None
    stage: RevisionStage
    code_hash: str
    semantic_fingerprint: str
    scene_hashes: Mapping[str, str]
    render_manifest_hash: str | None
    changed_scene_ids: Sequence[str]
    patch_scope: PatchScope
    created_by: RevisionCreator
    attempt: int
    schema_version: int = field(default=REVISION_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        require_non_empty_string(self.revision_id, "revision_id")
        require_optional_string(self.parent_revision_id, "parent_revision_id")
        object.__setattr__(
            self, "stage", require_enum(self.stage, RevisionStage, "stage")
        )
        require_sha256(self.code_hash, "code_hash")
        require_sha256(self.semantic_fingerprint, "semantic_fingerprint")
        object.__setattr__(
            self,
            "scene_hashes",
            _freeze_scene_hashes(self.scene_hashes),
        )
        require_optional_sha256(self.render_manifest_hash, "render_manifest_hash")
        object.__setattr__(
            self,
            "changed_scene_ids",
            freeze_identifier_sequence(self.changed_scene_ids, "changed_scene_ids"),
        )
        object.__setattr__(
            self,
            "patch_scope",
            require_enum(self.patch_scope, PatchScope, "patch_scope"),
        )
        object.__setattr__(
            self,
            "created_by",
            require_enum(self.created_by, RevisionCreator, "created_by"),
        )
        require_non_negative_int(self.attempt, "attempt")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "revision_id": self.revision_id,
            "parent_revision_id": self.parent_revision_id,
            "stage": self.stage.value,
            "code_hash": self.code_hash,
            "semantic_fingerprint": self.semantic_fingerprint,
            "scene_hashes": dict(self.scene_hashes),
            "render_manifest_hash": self.render_manifest_hash,
            "changed_scene_ids": list(self.changed_scene_ids),
            "patch_scope": self.patch_scope.value,
            "created_by": self.created_by.value,
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, data: object) -> Revision:
        payload = validate_contract_dict(
            data, _FIELDS, REVISION_SCHEMA_VERSION, cls.__name__
        )
        return cls(
            revision_id=payload["revision_id"],  # type: ignore[arg-type]
            parent_revision_id=payload["parent_revision_id"],  # type: ignore[arg-type]
            stage=require_enum(payload["stage"], RevisionStage, "stage"),
            code_hash=payload["code_hash"],  # type: ignore[arg-type]
            semantic_fingerprint=payload["semantic_fingerprint"],  # type: ignore[arg-type]
            scene_hashes=require_wire_object(payload["scene_hashes"], "scene_hashes"),
            render_manifest_hash=payload["render_manifest_hash"],  # type: ignore[arg-type]
            changed_scene_ids=require_wire_array(
                payload["changed_scene_ids"], "changed_scene_ids"
            ),
            patch_scope=require_enum(payload["patch_scope"], PatchScope, "patch_scope"),
            created_by=require_enum(
                payload["created_by"], RevisionCreator, "created_by"
            ),
            attempt=payload["attempt"],  # type: ignore[arg-type]
        )


def _freeze_scene_hashes(value: object) -> Mapping[str, str]:
    frozen = freeze_string_mapping(value, "scene_hashes")
    for scene_id, scene_hash in frozen.items():
        require_sha256(scene_hash, f"scene_hashes[{scene_id!r}]")
    return frozen
