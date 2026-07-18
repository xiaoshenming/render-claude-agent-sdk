from manim_quality.contracts import DeliveryDecision
from manim_quality.delivery.certificate import DeliveryCertificate, build_certificate
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.certificates import SemanticPreservationCertificate
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import SemanticDecision

from .test_consistency_gate import digest, gate_request


def test_delivery_certificate_binds_request_snapshot_render_and_decision() -> None:
    request = gate_request()
    gate = FinalConsistencyGate().evaluate(request)

    certificate = build_certificate(
        request.execution,
        request.snapshot,
        request.final_revision,
        request.render,
        request.logic,
        request.layout,
        request.semantic_preservation,
        gate,
        request.warnings,
        request.warning_decisions,
        request.versions,
        DeliveryDecision.ACCEPT,
    )
    payload = certificate.to_dict()

    assert payload["job_id"] == request.execution.job_id
    assert payload["decision"] == DeliveryDecision.ACCEPT.value
    assert payload["snapshot_version"] == request.snapshot.version
    assert payload["request_hash"] == request.execution.request_hash
    assert payload["expected_ordered_scene_ids"] == list(
        request.execution.ordered_scene_ids
    )
    assert payload["slice_hashes"] == dict(request.render.slice_hashes)
    assert payload["expected_assets_hash"] == request.execution.assets_hash
    assert payload["expected_external_dependencies_hash"] == (
        request.execution.external_dependencies_hash
    )
    assert payload["expected_render_config_hash"] == (
        request.execution.render_config_hash
    )
    assert payload["expected_environment_evidence_hash"] == (
        request.execution.environment_evidence_hash
    )
    assert payload["gate_version"] == request.versions.gate_version
    assert "certificate_hash" not in payload


def test_delivery_certificate_binds_semantic_certificate_and_evidence() -> None:
    request = gate_request()
    identity = ComponentIdentity(
        ComponentRole.LAYOUT_SEMANTIC_VERIFY,
        "semantic-verifier",
        digest("semantic-profile"),
        "semantic-session",
    )
    semantic = SemanticPreservationCertificate(
        request.execution.job_id,
        "logic-parent",
        digest("logic-code"),
        "layout-child",
        digest("layout-code"),
        request.execution.request_hash,
        request.execution.question_hash,
        request.execution.plan_hash,
        identity,
        request.versions.layout_semantic_verifier_version,
        digest("semantic-evidence"),
        SemanticDecision.PRESERVED,
    )
    gate = FinalConsistencyGate().evaluate(request)

    certificate = build_certificate(
        request.execution,
        request.snapshot,
        request.final_revision,
        request.render,
        request.logic,
        request.layout,
        semantic,
        gate,
        request.warnings,
        request.warning_decisions,
        request.versions,
        DeliveryDecision.ACCEPT,
    )

    assert certificate.to_dict()["semantic_preservation_hash"] == semantic.hash
    assert certificate.to_dict()["semantic_preservation_evidence_hash"] == (
        semantic.evidence_hash
    )


def test_delivery_certificate_canonicalizes_original_nested_input() -> None:
    original = {"nested": {"items": [{"value": "original"}]}}
    certificate = DeliveryCertificate(original)
    payload_before = certificate.payload
    hash_before = certificate.hash

    original["nested"]["items"][0]["value"] = "mutated"

    assert certificate.payload == payload_before
    assert certificate.hash == hash_before
    assert certificate.to_dict()["nested"]["items"][0]["value"] == "original"


def test_delivery_certificate_to_dict_returns_deep_fresh_copy() -> None:
    certificate = DeliveryCertificate({"nested": {"items": [{"value": "original"}]}})
    payload_before = certificate.payload
    hash_before = certificate.hash
    returned = certificate.to_dict()

    returned["nested"]["items"][0]["value"] = "mutated"

    assert certificate.payload == payload_before
    assert certificate.hash == hash_before
    assert certificate.to_dict()["nested"]["items"][0]["value"] == "original"
