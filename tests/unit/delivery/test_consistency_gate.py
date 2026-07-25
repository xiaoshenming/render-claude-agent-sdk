from dataclasses import replace

import pytest

from manim_quality.contracts import (
    PatchScope,
    QualityState,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.delivery.gate_models import FinalGateRequest
from manim_quality.orchestrator.certificates import LayoutCertificate, LogicCertificate
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import (
    AgentIdentity,
    ExecutionRequest,
    RenderBinding,
    VersionBindings,
)
from manim_quality.orchestrator.revision_models import BoundRevision
from manim_quality.revisions import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_text,
)
from manim_quality.revisions.store import QualityJobSnapshot

SOURCE = """\
class Lesson(Scene):
    def construct(self):
        self.add(Dot())

class Outro(Scene):
    def construct(self):
        self.add(Text("Done"))
"""


def digest(value: str) -> str:
    return sha256_text(value)


def versions() -> VersionBindings:
    agent = AgentIdentity("model-v1", "prompt-v1", "tools-v1")
    return VersionBindings(
        "config-v1",
        "schema-v1",
        "renderer-v1",
        "environment-v1",
        agent,
        agent,
        agent,
        "logic-validator-v1",
        "layout-detector-v1",
        "layout-policy-v1",
        agent,
        "layout-recheck-v1",
        "layout-semantic-v1",
        "warning-policy-v1",
        "gate-v1",
    )


def semantic_verifier_identity() -> ComponentIdentity:
    return ComponentIdentity(
        ComponentRole.LAYOUT_SEMANTIC_VERIFY,
        "semantic-verifier",
        digest("semantic-profile"),
        "semantic-session",
    )


def execution() -> ExecutionRequest:
    return ExecutionRequest(
        "job-1",
        "run-1",
        digest("request"),
        digest("question"),
        digest("plan"),
        SOURCE,
        "artifact://code/original",
        "artifact://render/original",
        digest("render-config"),
        digest("assets"),
        digest("dependencies"),
        ("Lesson", "Outro"),
        digest("environment-evidence"),
        versions(),
    )


def bound_revision() -> BoundRevision:
    revision = Revision(
        "baseline",
        None,
        RevisionStage.BASELINE,
        code_hash(SOURCE),
        semantic_fingerprint(SOURCE),
        scene_fingerprints(SOURCE),
        digest("manifest"),
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.SYSTEM,
        0,
    )
    return BoundRevision(revision, SOURCE)


def render(bound: BoundRevision) -> RenderBinding:
    return RenderBinding(
        bound.revision_id,
        bound.code_hash,
        bound.render_manifest_hash,
        digest("manifest-evidence"),
        digest("manifest-content"),
        digest("video"),
        tuple(bound.scene_hashes),
        bound.scene_hashes,
        {name: digest(f"slice:{name}") for name in bound.scene_hashes},
        digest("assets"),
        digest("dependencies"),
        digest("render-config"),
        versions().renderer_version,
        versions().environment_version,
        digest("environment-evidence"),
        True,
        False,
    )


def gate_request() -> FinalGateRequest:
    expected = execution()
    bound = bound_revision()
    rendered = render(bound)
    logic = LogicCertificate(
        expected.job_id,
        bound.revision_id,
        bound.code_hash,
        bound.semantic_fingerprint,
        bound.layout_invariant_fingerprint,
        expected.request_hash,
        expected.question_hash,
        expected.plan_hash,
        expected.code_ref,
        expected.render_manifest_ref,
        digest("logic-assessment"),
        rendered.render_manifest_hash,
        rendered.manifest_evidence_hash,
        versions(),
    )
    layout = LayoutCertificate(
        expected.job_id,
        bound.revision_id,
        bound.code_hash,
        rendered.render_manifest_hash,
        bound.revision_id,
        expected.request_hash,
        digest("layout-assessment"),
        rendered.manifest_evidence_hash,
        0,
        versions(),
    )
    snapshot = QualityJobSnapshot(
        expected.job_id,
        5,
        QualityState.FINAL_CONSISTENCY_GATE,
        bound.revision_id,
        bound.revision_id,
        bound.revision_id,
        None,
        bound.render_manifest_hash,
        logic.hash,
        layout.hash,
        None,
    )
    return FinalGateRequest(
        expected,
        snapshot,
        bound,
        bound,
        rendered,
        logic,
        layout,
        None,
        semantic_verifier_identity(),
        versions(),
        (),
        (),
    )


def test_gate_accepts_fully_bound_evidence() -> None:
    assert FinalConsistencyGate().evaluate(gate_request()).passed


def test_gate_rejects_authoritative_request_substitution() -> None:
    request = gate_request()
    substituted = replace(
        request.execution, question_hash=digest("substituted-question")
    )

    result = FinalConsistencyGate().evaluate(replace(request, execution=substituted))

    assert not result.passed
    assert "request.question_hash" in result.failures


@pytest.mark.parametrize(
    ("field_name", "failure"),
    [
        ("render_config_hash", "render.render_config_hash"),
        ("assets_hash", "render.assets_hash"),
        ("external_dependencies_hash", "render.external_dependencies_hash"),
    ],
)
def test_gate_rejects_renderer_supplied_authority_substitution(
    field_name: str, failure: str
) -> None:
    request = gate_request()
    attacked_render = replace(request.render, **{field_name: digest("attacker")})

    result = FinalConsistencyGate().evaluate(replace(request, render=attacked_render))

    assert not result.passed
    assert failure in result.failures


def test_gate_rejects_scene_order_substitution() -> None:
    request = gate_request()
    attacked_order = tuple(reversed(request.render.ordered_scene_ids))
    attacked_render = replace(
        request.render,
        ordered_scene_ids=attacked_order,
        scene_hashes={
            name: request.render.scene_hashes[name] for name in attacked_order
        },
        slice_hashes={
            name: request.render.slice_hashes[name] for name in attacked_order
        },
    )

    result = FinalConsistencyGate().evaluate(replace(request, render=attacked_render))

    assert not result.passed
    assert "render.scene_order" in result.failures


@pytest.mark.parametrize("suffix", ["z" * 64, "A" * 64, "0" * 63 + "g"])
def test_render_binding_rejects_noncanonical_final_video_hash(suffix: str) -> None:
    request = gate_request()

    with pytest.raises(ValueError, match="canonical sha256"):
        replace(request.render, final_video_hash="sha256:" + suffix)


@pytest.mark.parametrize("suffix", ["z" * 64, "A" * 64, "0" * 63 + "g"])
def test_render_binding_rejects_noncanonical_slice_hash(suffix: str) -> None:
    request = gate_request()
    slices = dict(request.render.slice_hashes)
    slices[request.render.ordered_scene_ids[0]] = "sha256:" + suffix

    with pytest.raises(ValueError, match="canonical sha256"):
        replace(request.render, slice_hashes=slices)
