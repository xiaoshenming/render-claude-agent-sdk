"""Canonical final certificate construction without circular self hashes."""

import json
from collections.abc import Mapping
from dataclasses import dataclass

from manim_quality.contracts import DeliveryDecision
from manim_quality.orchestrator.certificates import (
    LayoutCertificate,
    LogicCertificate,
    SemanticPreservationCertificate,
)
from manim_quality.orchestrator.models import (
    ExecutionRequest,
    RenderBinding,
    VersionBindings,
    WarningPolicyDecision,
    WarningRecord,
)
from manim_quality.orchestrator.revision_models import BoundRevision
from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.revisions.store import QualityJobSnapshot

from .evidence import canonical_bytes
from .gate_models import FinalGateResult


@dataclass(frozen=True, slots=True, init=False)
class DeliveryCertificate:
    _payload: bytes

    def __init__(self, payload_data: Mapping[str, object]) -> None:
        object.__setattr__(self, "_payload", canonical_bytes(payload_data))

    @property
    def hash(self) -> str:
        return sha256_bytes(self._payload)

    @property
    def payload(self) -> bytes:
        return self._payload

    def to_dict(self) -> dict[str, object]:
        value = json.loads(self._payload)
        if not isinstance(value, dict):
            raise TypeError("certificate payload must decode to an object")
        return value


def build_certificate(
    execution: ExecutionRequest,
    snapshot: QualityJobSnapshot,
    final: BoundRevision,
    render: RenderBinding,
    logic: LogicCertificate,
    layout: LayoutCertificate,
    semantic_preservation: SemanticPreservationCertificate | None,
    gate: FinalGateResult,
    warnings: tuple[WarningRecord, ...],
    warning_decisions: tuple[WarningPolicyDecision, ...],
    versions: VersionBindings,
    decision: DeliveryDecision,
) -> DeliveryCertificate:
    if not gate.passed:
        raise ValueError("cannot certify a failed final gate")
    if gate.snapshot_version != snapshot.version:
        raise ValueError("gate does not bind the delivery snapshot")
    payload = {
        **_request_payload(execution),
        **_render_payload(final, render),
        **_evidence_payload(
            logic, layout, semantic_preservation, gate, warnings, warning_decisions
        ),
        "decision": decision.value,
        "snapshot_version": snapshot.version,
        "versions": versions.to_dict(),
    }
    return DeliveryCertificate(payload)


def _request_payload(execution: ExecutionRequest) -> dict[str, object]:
    return {
        "code_ref": execution.code_ref,
        "expected_assets_hash": execution.assets_hash,
        "expected_environment_evidence_hash": execution.environment_evidence_hash,
        "expected_external_dependencies_hash": execution.external_dependencies_hash,
        "expected_ordered_scene_ids": list(execution.ordered_scene_ids),
        "expected_render_config_hash": execution.render_config_hash,
        "job_id": execution.job_id,
        "plan_hash": execution.plan_hash,
        "question_hash": execution.question_hash,
        "render_manifest_ref": execution.render_manifest_ref,
        "request_hash": execution.request_hash,
    }


def _render_payload(final: BoundRevision, render: RenderBinding) -> dict[str, object]:
    return {
        "code_hash": final.code_hash,
        "environment_complete": render.environment_complete,
        "environment_uncertain": render.environment_uncertain,
        "environment_version": render.environment_version,
        "final_video_hash": render.final_video_hash,
        "layout_invariant_fingerprint": final.layout_invariant_fingerprint,
        "render_content_hash": render.manifest_content_hash,
        "render_evidence_hash": render.manifest_evidence_hash,
        "render_manifest_hash": render.render_manifest_hash,
        "renderer_version": render.renderer_version,
        "revision_id": final.revision_id,
        "scene_hashes": dict(render.scene_hashes),
        "schema_version": 1,
        "semantic_fingerprint": final.semantic_fingerprint,
        "slice_hashes": dict(render.slice_hashes),
    }


def _evidence_payload(
    logic: LogicCertificate,
    layout: LayoutCertificate,
    semantic: SemanticPreservationCertificate | None,
    gate: FinalGateResult,
    warnings: tuple[WarningRecord, ...],
    warning_decisions: tuple[WarningPolicyDecision, ...],
) -> dict[str, object]:
    return {
        "gate_evidence_hash": gate.evidence_hash,
        "gate_version": gate.gate_version,
        "layout_certificate_hash": layout.hash,
        "logic_certificate_hash": logic.hash,
        "semantic_preservation_hash": None if semantic is None else semantic.hash,
        "semantic_preservation_evidence_hash": (
            None if semantic is None else semantic.evidence_hash
        ),
        "warning_evidence_hashes": [item.evidence_hash for item in warnings],
        "warning_policy_hashes": [item.evidence_hash for item in warning_decisions],
    }
