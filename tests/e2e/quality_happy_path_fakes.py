from __future__ import annotations

from manim_quality.contracts import PatchScope, RevisionCreator, RevisionStage
from manim_quality.orchestrator.certificates import (
    LayoutCertificate,
    LogicCertificate,
    SemanticPreservationCertificate,
)
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import (
    RenderBinding,
    RenderedCandidate,
    SemanticDecision,
    WarningPolicyDecision,
)
from manim_quality.orchestrator.revision_models import BoundRevision, RepairProposal
from manim_quality.revisions import sha256_text


def digest(value: str) -> str:
    return sha256_text(value)


class FakeRepair:
    def __init__(self, stage: RevisionStage) -> None:
        self.stage = stage
        role = ComponentRole.LAYOUT_REPAIR if stage is RevisionStage.LAYOUT_REPAIR else ComponentRole.LOGIC_REPAIR
        label = role.value.lower()
        self.identity = ComponentIdentity(role, f"fake-{label}", digest(f"profile:{label}"), f"session:{label}")

    def propose(self, parent, assessment, request) -> RepairProposal:
        layout = self.stage is RevisionStage.LAYOUT_REPAIR
        source = parent.source_code.replace("shift(RIGHT)", "shift(2 * RIGHT)") if layout else parent.source_code.replace("Dot()", "Circle()")
        return RepairProposal(
            "layout-fixed" if layout else "logic-fixed", parent.revision_id, self.stage, source,
            ("Lesson",), PatchScope.LAYOUT_ONLY if layout else PatchScope.SCENE_LOGIC,
            RevisionCreator.OVERLAP_AGENT if layout else RevisionCreator.LOGIC_AGENT, 1,
        )


class FakeRender:
    def render(self, candidate, request) -> RenderedCandidate:
        bound = candidate.materialize(digest(f"manifest:{candidate.revision_id}"))
        return RenderedCandidate(bound, self.bind(bound, request))

    def bind(self, revision: BoundRevision, request) -> RenderBinding:
        return RenderBinding(
            revision.revision_id, revision.code_hash, revision.render_manifest_hash,
            digest(f"manifest-evidence:{revision.revision_id}"), digest(f"manifest-content:{revision.revision_id}"),
            digest(f"video:{revision.revision_id}"), tuple(revision.scene_hashes), revision.scene_hashes,
            {name: digest(f"slice:{revision.revision_id}:{name}") for name in revision.scene_hashes},
            digest("assets"), digest("dependencies"), digest("render-config"),
            request.versions.renderer_version, request.versions.environment_version,
            digest("environment-evidence"), True, False,
        )
