"""Ports used by the user modification application service."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from manim_quality.contracts import Revision
from manim_quality.rendering.interfaces import RenderEvidence, RenderRequest

from .coder import ModificationCoderResult
from .models import ApprovalReceipt, ModificationContext, ModificationDraft
from .planner import ModificationPlan


class ModificationContextProvider(Protocol):
    def load(self, tenant_id: str, job_id: str) -> ModificationContext: ...


class ModificationExecutor(Protocol):
    def patch_source(
        self,
        *,
        run_id: str,
        instruction: str,
        source_code: str,
        plan: ModificationPlan,
    ) -> ModificationCoderResult: ...


class PreviewRenderer(Protocol):
    def render(self, request: RenderRequest) -> RenderEvidence: ...


class ModificationRepository(Protocol):
    def create(self, draft: ModificationDraft) -> ModificationDraft: ...

    def get(self, tenant_id: str, job_id: str, draft_id: str) -> ModificationDraft: ...

    def approve(
        self,
        draft: ModificationDraft,
        revision: Revision,
        quality_baseline: Revision,
        quality_job_id: str,
        queue_payload: bytes,
        queue_request_hash: str,
        stage_run_id: str,
        *,
        expected_version: int,
        now: datetime,
    ) -> ApprovalReceipt: ...

    def discard(
        self,
        tenant_id: str,
        job_id: str,
        draft_id: str,
        *,
        expected_version: int,
    ) -> ModificationDraft: ...

    def close(self) -> None: ...
