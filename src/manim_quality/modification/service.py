"""Application service for preview, approval, and discard of user edits."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from manim_quality.revisions.fingerprint import sha256_text

from .approval import build_approval
from .models import ApprovalReceipt, DraftState, ModificationDraft
from .ports import (
    ModificationContextProvider,
    ModificationExecutor,
    ModificationRepository,
    PreviewRenderer,
)
from .preview import build_preview_draft


class ModificationFailed(RuntimeError):
    pass


class ModificationService:
    def __init__(
        self,
        repository: ModificationRepository,
        contexts: ModificationContextProvider,
        executor: ModificationExecutor,
        renderer: PreviewRenderer,
    ) -> None:
        self._repository = repository
        self._contexts = contexts
        self._executor = executor
        self._renderer = renderer

    def close(self) -> None:
        self._repository.close()

    def create_preview(
        self,
        *,
        tenant_id: str,
        job_id: str,
        instruction: str,
        target_scene_ids: tuple[str, ...],
        idempotency_key: str,
    ) -> ModificationDraft:
        context = self._contexts.load(tenant_id, job_id)
        _require_context(context, tenant_id, job_id)
        request_hash = _request_hash(
            tenant_id, job_id, instruction, target_scene_ids, idempotency_key
        )
        draft_id = _draft_id(tenant_id, job_id, idempotency_key)
        existing = _existing(self._repository, tenant_id, job_id, draft_id)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ModificationFailed("idempotency identity has different payload")
            return existing
        draft = build_preview_draft(
            context,
            self._executor,
            self._renderer,
            draft_id=draft_id,
            request_hash=request_hash,
            instruction=instruction,
            target_scene_ids=target_scene_ids,
            idempotency_key=idempotency_key,
        )
        return self._repository.create(draft)

    def get(self, tenant_id: str, job_id: str, draft_id: str) -> ModificationDraft:
        return self._repository.get(tenant_id, job_id, draft_id)

    def approve(
        self,
        tenant_id: str,
        job_id: str,
        draft_id: str,
        *,
        expected_version: int,
        now: datetime | None = None,
    ) -> ApprovalReceipt:
        draft = self.get(tenant_id, job_id, draft_id)
        if (
            draft.state is DraftState.APPROVED
            and draft.quality_run_id
            and draft.quality_job_id
        ):
            return ApprovalReceipt(draft, draft.quality_run_id, draft.quality_job_id)
        if draft.state is not DraftState.PREVIEW_READY:
            raise ModificationFailed(f"cannot approve {draft.state.value} draft")
        context = self._contexts.load(tenant_id, job_id)
        _require_context(context, tenant_id, job_id)
        command = build_approval(context.quality_request, draft)
        return self._repository.approve(
            draft,
            command.revision,
            command.quality_baseline,
            command.quality_job_id,
            command.payload,
            command.request_hash,
            command.stage_run_id,
            expected_version=expected_version,
            now=now or datetime.now(UTC),
        )

    def discard(
        self,
        tenant_id: str,
        job_id: str,
        draft_id: str,
        *,
        expected_version: int,
    ) -> ModificationDraft:
        return self._repository.discard(
            tenant_id,
            job_id,
            draft_id,
            expected_version=expected_version,
        )


def _request_hash(
    tenant_id: str,
    job_id: str,
    instruction: str,
    targets: tuple[str, ...],
    idempotency_key: str,
) -> str:
    value = json.dumps(
        [tenant_id, job_id, instruction, list(targets), idempotency_key],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return sha256_text(value)


def _draft_id(tenant_id: str, job_id: str, idempotency_key: str) -> str:
    identity = json.dumps(
        [tenant_id, job_id, idempotency_key],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"draft-{sha256_text(identity)[7:31]}"


def _existing(repository, tenant_id, job_id, draft_id):
    try:
        return repository.get(tenant_id, job_id, draft_id)
    except KeyError:
        return None


def _require_context(context, tenant_id: str, job_id: str) -> None:
    if context.tenant_id != tenant_id or context.job_id != job_id:
        raise ModificationFailed("context tenant or job mismatch")


__all__ = ["ModificationFailed", "ModificationService"]
