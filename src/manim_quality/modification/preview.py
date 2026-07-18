"""Targeted preview construction for a user modification draft."""

from __future__ import annotations

from dataclasses import replace

from manim_quality.rendering.impact import analyze_source
from manim_quality.revisions.fingerprint import code_hash

from .models import DraftState, ModificationDraft
from .planner import plan_modification, validate_modification


def build_preview_draft(
    context,
    executor,
    renderer,
    *,
    draft_id: str,
    request_hash: str,
    instruction: str,
    target_scene_ids: tuple[str, ...],
    idempotency_key: str,
) -> ModificationDraft:
    plan = plan_modification(context.source_code, target_scene_ids)
    result = executor.patch_source(
        run_id=f"modify:{draft_id}",
        instruction=instruction,
        source_code=context.source_code,
        plan=plan,
    )
    changed = validate_modification(context.source_code, result.source_code, plan)
    candidate_id = f"user-mod-{request_hash[7:39]}"
    preview_id = f"baseline-{context.job_id}:mod:{draft_id[6:22]}"
    request = _render_request(context, result.source_code, plan, preview_id)
    preview = renderer.render(request)
    return _draft(
        context,
        draft_id,
        request_hash,
        idempotency_key,
        instruction,
        candidate_id,
        changed,
        result.source_code,
        preview,
    )


def _render_request(context, source_code, plan, revision_id):
    impact = analyze_source(source_code, plan.ordered_scene_ids)
    return replace(
        context.preview_request,
        revision_id=revision_id,
        source_code=source_code,
        code_hash=code_hash(source_code),
        scene_hashes=impact.scene_hashes,
        ordered_scene_ids=plan.ordered_scene_ids,
    )


def _draft(
    context,
    draft_id,
    request_hash,
    idempotency_key,
    instruction,
    candidate_id,
    changed,
    source_code,
    preview,
) -> ModificationDraft:
    failed = not preview.succeeded or preview.manifest is None
    manifest = None if failed else preview.manifest
    reason = None
    if failed:
        reason = f"targeted preview failed: {preview.failure_message or 'unknown'}"
    return ModificationDraft(
        draft_id=draft_id,
        tenant_id=context.tenant_id,
        job_id=context.job_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        parent_revision_id=context.parent_revision_id,
        candidate_revision_id=candidate_id,
        instruction=instruction,
        target_scene_ids=changed,
        candidate_source=source_code,
        preview_manifest_hash=None if failed else manifest.hash,
        preview_video_hash=None if failed else manifest.final_video.hash,
        state=DraftState.FAILED if failed else DraftState.PREVIEW_READY,
        failure_reason=reason,
    )
