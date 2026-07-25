from dataclasses import FrozenInstanceError, replace

import pytest

from manim_quality.contracts import (
    PatchScope,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.orchestrator.checkpoints import require_proposal
from manim_quality.orchestrator.models import StageAction, StageAssessment
from manim_quality.orchestrator.revision_models import (
    BoundRevision,
    CandidateRevision,
    RepairProposal,
)
from manim_quality.revisions import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_text,
)

SOURCE = """\
class Lesson(Scene):
    def construct(self):
        dot = Dot()
        dot.shift(RIGHT)
"""

LAYOUT_EDIT = SOURCE.replace("shift(RIGHT)", "shift(2 * RIGHT)")
LOGIC_EDIT = SOURCE.replace("Dot()", "Circle()")


def proposal(source: str, stage: RevisionStage) -> RepairProposal:
    return RepairProposal(
        revision_id="candidate",
        parent_revision_id="baseline",
        stage=stage,
        source_code=source,
        changed_scene_ids=("Lesson",),
        patch_scope=(
            PatchScope.LAYOUT_ONLY
            if stage is RevisionStage.LAYOUT_REPAIR
            else PatchScope.SCENE_LOGIC
        ),
        created_by=(
            RevisionCreator.OVERLAP_AGENT
            if stage is RevisionStage.LAYOUT_REPAIR
            else RevisionCreator.LOGIC_AGENT
        ),
        attempt=1,
    )


def test_repair_assessment_contains_no_candidate() -> None:
    assessment = StageAssessment(StageAction.REPAIR, sha256_text("assessment"))

    assert assessment.action is StageAction.REPAIR
    assert not hasattr(assessment, "candidate")


def test_candidate_identities_are_derived_from_immutable_source() -> None:
    candidate = CandidateRevision.from_proposal(
        proposal(LOGIC_EDIT, RevisionStage.LOGIC_REPAIR)
    )

    assert candidate.code_hash == code_hash(LOGIC_EDIT)
    assert candidate.scene_hashes == scene_fingerprints(LOGIC_EDIT)
    assert candidate.semantic_fingerprint == semantic_fingerprint(LOGIC_EDIT)
    with pytest.raises(FrozenInstanceError):
        candidate.source_code = SOURCE  # type: ignore[misc]


def test_bound_revision_rejects_substituted_source() -> None:
    revision = Revision(
        "baseline",
        None,
        RevisionStage.BASELINE,
        code_hash(SOURCE),
        semantic_fingerprint(SOURCE),
        scene_fingerprints(SOURCE),
        sha256_text("manifest"),
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.SYSTEM,
        0,
    )

    assert BoundRevision(revision, SOURCE).source_code == SOURCE
    with pytest.raises(ValueError, match="source"):
        BoundRevision(revision, LOGIC_EDIT)


def test_layout_invariant_is_computed_from_parent_and_candidate_sources() -> None:
    parent = CandidateRevision.from_proposal(
        proposal(SOURCE, RevisionStage.LOGIC_REPAIR)
    )
    layout = CandidateRevision.from_proposal(
        proposal(LAYOUT_EDIT, RevisionStage.LAYOUT_REPAIR)
    )
    logic = CandidateRevision.from_proposal(
        proposal(LOGIC_EDIT, RevisionStage.LAYOUT_REPAIR)
    )

    assert parent.layout_invariant_fingerprint == layout.layout_invariant_fingerprint
    assert parent.layout_invariant_fingerprint != logic.layout_invariant_fingerprint


@pytest.mark.parametrize(
    "changes",
    [
        {"patch_scope": PatchScope.LAYOUT_ONLY},
        {"created_by": RevisionCreator.OVERLAP_AGENT},
    ],
)
def test_logic_proposal_rejects_mismatched_scope_or_creator(changes) -> None:
    parent = BoundRevision(
        Revision(
            "baseline",
            None,
            RevisionStage.BASELINE,
            code_hash(SOURCE),
            semantic_fingerprint(SOURCE),
            scene_fingerprints(SOURCE),
            sha256_text("manifest"),
            (),
            PatchScope.FULL_CANDIDATE,
            RevisionCreator.SYSTEM,
            0,
        ),
        SOURCE,
    )
    invalid = replace(
        proposal(LOGIC_EDIT, RevisionStage.LOGIC_REPAIR),
        **changes,
    )

    with pytest.raises(ValueError, match="scope or creator"):
        require_proposal(invalid, parent, RevisionStage.LOGIC_REPAIR)


@pytest.mark.parametrize(
    "changes",
    [
        {"patch_scope": PatchScope.SCENE_LOGIC},
        {"created_by": RevisionCreator.LOGIC_AGENT},
    ],
)
def test_layout_proposal_rejects_mismatched_scope_or_creator(changes) -> None:
    parent = BoundRevision(
        Revision(
            "baseline",
            None,
            RevisionStage.BASELINE,
            code_hash(SOURCE),
            semantic_fingerprint(SOURCE),
            scene_fingerprints(SOURCE),
            sha256_text("manifest"),
            (),
            PatchScope.FULL_CANDIDATE,
            RevisionCreator.SYSTEM,
            0,
        ),
        SOURCE,
    )
    invalid = replace(
        proposal(LAYOUT_EDIT, RevisionStage.LAYOUT_REPAIR),
        **changes,
    )

    with pytest.raises(ValueError, match="scope or creator"):
        require_proposal(invalid, parent, RevisionStage.LAYOUT_REPAIR)
