"""LLM-free final binding validation."""

from .evidence import content_hash
from .gate_models import FinalGateRequest, FinalGateResult
from .render_checks import render_failures


class FinalConsistencyGate:
    def evaluate(self, request: FinalGateRequest) -> FinalGateResult:
        failures = tuple(_failures(request))
        evidence_hash = content_hash(_gate_evidence(request, failures))
        return FinalGateResult(
            not failures,
            failures,
            evidence_hash,
            request.snapshot.version,
            request.versions.gate_version,
        )


def _failures(request: FinalGateRequest):
    yield from _request_failures(request)
    yield from _snapshot_failures(request)
    yield from render_failures(request)
    yield from _logic_failures(request)
    yield from _layout_failures(request)
    yield from _semantic_failures(request)
    yield from _warning_failures(request)


def _request_failures(request: FinalGateRequest):
    expected = request.execution
    logic = request.logic
    if logic.job_id != expected.job_id:
        yield "request.job_id"
    for name in ("request_hash", "question_hash", "plan_hash"):
        if getattr(logic, name) != getattr(expected, name):
            yield f"request.{name}"
    if logic.code_ref != expected.code_ref:
        yield "request.code_ref"
    if logic.render_manifest_ref != expected.render_manifest_ref:
        yield "request.render_manifest_ref"
    if request.layout.request_hash != expected.request_hash:
        yield "layout.request_hash"


def _snapshot_failures(request: FinalGateRequest):
    snapshot = request.snapshot
    if snapshot.job_id != request.execution.job_id:
        yield "snapshot.job_id"
    if snapshot.logic_certified_revision_id != request.logic_checkpoint.revision_id:
        yield "snapshot.logic_checkpoint"
    if snapshot.logic_certified_evidence_hash != request.logic.hash:
        yield "snapshot.logic_certificate"
    if snapshot.layout_certified_revision_id != request.final_revision.revision_id:
        yield "snapshot.layout_checkpoint"
    if snapshot.layout_certified_evidence_hash != request.layout.hash:
        yield "snapshot.layout_certificate"
    if snapshot.state.value != "FINAL_CONSISTENCY_GATE":
        yield "snapshot.state"


def _logic_failures(request: FinalGateRequest):
    bound = request.logic_checkpoint
    logic = request.logic
    expected = (
        bound.revision_id,
        bound.code_hash,
        bound.semantic_fingerprint,
        bound.layout_invariant_fingerprint,
        bound.render_manifest_hash,
        request.versions,
    )
    actual = (
        logic.revision_id,
        logic.code_hash,
        logic.semantic_fingerprint,
        logic.layout_invariant_fingerprint,
        logic.render_manifest_hash,
        logic.versions,
    )
    if actual != expected:
        yield "logic.binding"


def _layout_failures(request: FinalGateRequest):
    final = request.final_revision
    logic = request.logic_checkpoint
    layout = request.layout
    expected = (
        final.revision_id,
        final.code_hash,
        final.render_manifest_hash,
        logic.revision_id,
        request.render.manifest_evidence_hash,
        0,
        request.versions,
    )
    actual = (
        layout.revision_id,
        layout.code_hash,
        layout.render_manifest_hash,
        layout.logic_checkpoint_revision_id,
        layout.render_evidence_hash,
        layout.blocking_issues,
        layout.versions,
    )
    if actual != expected:
        yield "layout.binding"


def _semantic_failures(request: FinalGateRequest):
    changed = request.final_revision.revision_id != request.logic_checkpoint.revision_id
    certificate = request.semantic_preservation
    if changed and certificate is None:
        yield "layout.semantic_certificate_missing"
        return
    if not changed and certificate is not None:
        yield "layout.semantic_certificate_unexpected"
        return
    if certificate is None:
        return
    expected = (
        request.execution.job_id,
        request.logic_checkpoint.revision_id,
        request.logic_checkpoint.code_hash,
        request.final_revision.revision_id,
        request.final_revision.code_hash,
        request.execution.request_hash,
        request.execution.question_hash,
        request.execution.plan_hash,
        request.semantic_verifier_identity,
        request.versions.layout_semantic_verifier_version,
        certificate.evidence_hash,
        "PRESERVED",
    )
    actual = (
        certificate.job_id,
        certificate.logic_revision_id,
        certificate.logic_code_hash,
        certificate.final_revision_id,
        certificate.final_code_hash,
        certificate.request_hash,
        certificate.question_hash,
        certificate.plan_hash,
        certificate.verifier_identity,
        certificate.verifier_version,
        certificate.evidence_hash,
        certificate.decision.value,
    )
    if actual != expected:
        yield "layout.semantic_binding"


def _warning_failures(request: FinalGateRequest):
    certificate_warnings = request.logic.warnings + request.layout.warnings
    if certificate_warnings != request.warnings:
        yield "warning.envelope"
    authorized: list[str] = []
    for decision in request.warning_decisions:
        if not decision.authorized:
            yield "warning.unauthorized"
        if decision.policy_version != request.versions.warning_policy_version:
            yield "warning.policy_version"
        authorized.extend(decision.warning_evidence_hashes)
    expected = [item.evidence_hash for item in request.warnings]
    if sorted(authorized) != sorted(expected):
        yield "warning.evidence"


def _gate_evidence(request: FinalGateRequest, failures: tuple[str, ...]):
    return {
        "failures": list(failures),
        "gate_version": request.versions.gate_version,
        "layout_certificate_hash": request.layout.hash,
        "logic_certificate_hash": request.logic.hash,
        "semantic_preservation_hash": (
            None
            if request.semantic_preservation is None
            else request.semantic_preservation.hash
        ),
        "semantic_preservation_evidence_hash": (
            None
            if request.semantic_preservation is None
            else request.semantic_preservation.evidence_hash
        ),
        "semantic_verifier_identity": request.semantic_verifier_identity.to_dict(),
        "render_content_hash": request.render.manifest_content_hash,
        "render_evidence_hash": request.render.manifest_evidence_hash,
        "request": {
            "assets_hash": request.execution.assets_hash,
            "code_ref": request.execution.code_ref,
            "environment_evidence_hash": (request.execution.environment_evidence_hash),
            "external_dependencies_hash": (
                request.execution.external_dependencies_hash
            ),
            "ordered_scene_ids": list(request.execution.ordered_scene_ids),
            "plan_hash": request.execution.plan_hash,
            "question_hash": request.execution.question_hash,
            "render_config_hash": request.execution.render_config_hash,
            "render_manifest_ref": request.execution.render_manifest_ref,
            "request_hash": request.execution.request_hash,
        },
        "revision_id": request.final_revision.revision_id,
        "snapshot_version": request.snapshot.version,
        "versions": request.versions.to_dict(),
        "warning_policy_hashes": [
            item.evidence_hash for item in request.warning_decisions
        ],
    }
