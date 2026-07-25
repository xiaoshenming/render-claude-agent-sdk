"""Source-bound immutable revision models owned by the platform."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from manim_quality.contracts import (
    PatchScope,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.layout.policy import layout_invariant_fingerprint
from manim_quality.revisions import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
)

from ._model_validation import require_text


@dataclass(frozen=True, slots=True)
class BoundRevision:
    revision: Revision
    source_code: str
    layout_invariant_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.revision, Revision):
            raise TypeError("revision must be a Revision")
        require_text(self.source_code, "source_code")
        if self.revision.code_hash != code_hash(self.source_code):
            raise ValueError("source does not match revision code_hash")
        if dict(self.revision.scene_hashes) != dict(
            scene_fingerprints(self.source_code)
        ):
            raise ValueError("source does not match revision Scene hashes")
        if self.revision.semantic_fingerprint != semantic_fingerprint(self.source_code):
            raise ValueError("source does not match revision semantic fingerprint")
        object.__setattr__(
            self,
            "layout_invariant_fingerprint",
            layout_invariant_fingerprint(self.source_code),
        )

    def __getattr__(self, name: str) -> object:
        return getattr(self.revision, name)


@dataclass(frozen=True, slots=True)
class RepairProposal:
    revision_id: str
    parent_revision_id: str
    stage: RevisionStage
    source_code: str
    changed_scene_ids: Sequence[str]
    patch_scope: PatchScope
    created_by: RevisionCreator
    attempt: int

    def __post_init__(self) -> None:
        require_text(self.revision_id, "revision_id")
        require_text(self.parent_revision_id, "parent_revision_id")
        require_text(self.source_code, "source_code")
        if self.stage not in {RevisionStage.LOGIC_REPAIR, RevisionStage.LAYOUT_REPAIR}:
            raise ValueError("repair proposal requires a repair stage")
        object.__setattr__(self, "changed_scene_ids", tuple(self.changed_scene_ids))


@dataclass(frozen=True, slots=True)
class CandidateRevision:
    revision_id: str
    parent_revision_id: str
    stage: RevisionStage
    source_code: str
    changed_scene_ids: tuple[str, ...]
    patch_scope: PatchScope
    created_by: RevisionCreator
    attempt: int
    code_hash: str = field(init=False)
    semantic_fingerprint: str = field(init=False)
    scene_hashes: Mapping[str, str] = field(init=False)
    layout_invariant_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        require_text(self.source_code, "source_code")
        object.__setattr__(self, "code_hash", code_hash(self.source_code))
        object.__setattr__(
            self, "semantic_fingerprint", semantic_fingerprint(self.source_code)
        )
        object.__setattr__(
            self,
            "scene_hashes",
            MappingProxyType(dict(scene_fingerprints(self.source_code))),
        )
        object.__setattr__(
            self,
            "layout_invariant_fingerprint",
            layout_invariant_fingerprint(self.source_code),
        )

    @classmethod
    def from_proposal(cls, proposal: RepairProposal) -> CandidateRevision:
        if not isinstance(proposal, RepairProposal):
            raise TypeError("proposal must be a RepairProposal")
        return cls(
            proposal.revision_id,
            proposal.parent_revision_id,
            proposal.stage,
            proposal.source_code,
            tuple(proposal.changed_scene_ids),
            proposal.patch_scope,
            proposal.created_by,
            proposal.attempt,
        )

    def materialize(self, render_manifest_hash: str) -> BoundRevision:
        revision = Revision(
            self.revision_id,
            self.parent_revision_id,
            self.stage,
            self.code_hash,
            self.semantic_fingerprint,
            self.scene_hashes,
            render_manifest_hash,
            self.changed_scene_ids,
            self.patch_scope,
            self.created_by,
            self.attempt,
        )
        return BoundRevision(revision, self.source_code)
