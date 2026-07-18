"""Deterministic checks for final render identity and environment."""

from .gate_models import FinalGateRequest


def render_failures(request: FinalGateRequest):
    yield from _revision_failures(request)
    yield from _authority_failures(request)
    yield from _environment_failures(request)


def _revision_failures(request: FinalGateRequest):
    final = request.final_revision
    render = request.render
    if render.revision_id != final.revision_id:
        yield "render.revision_id"
    if render.code_hash != final.code_hash:
        yield "render.code_hash"
    if render.render_manifest_hash != final.render_manifest_hash:
        yield "render.manifest_hash"
    if dict(render.scene_hashes) != dict(final.scene_hashes):
        yield "render.scene_hashes"


def _authority_failures(request: FinalGateRequest):
    render = request.render
    expected = request.execution
    if render.ordered_scene_ids != expected.ordered_scene_ids:
        yield "render.scene_order"
    if tuple(render.scene_hashes) != expected.ordered_scene_ids:
        yield "render.scene_hash_order"
    if tuple(render.slice_hashes) != expected.ordered_scene_ids:
        yield "render.slice_hash_order"
    for name in (
        "render_config_hash",
        "assets_hash",
        "external_dependencies_hash",
        "environment_evidence_hash",
    ):
        if getattr(render, name) != getattr(expected, name):
            yield f"render.{name}"


def _environment_failures(request: FinalGateRequest):
    render = request.render
    if not render.environment_complete:
        yield "render.environment_incomplete"
    if render.environment_uncertain:
        yield "render.environment_uncertain"
    if render.renderer_version != request.versions.renderer_version:
        yield "render.renderer_version"
    if render.environment_version != request.versions.environment_version:
        yield "render.environment_version"
