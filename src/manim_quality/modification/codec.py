"""Store-neutral encoding for immutable modification drafts."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .models import DraftState, ModificationDraft


def draft_payload(draft: ModificationDraft) -> dict[str, object]:
    return {
        "parent_revision_id": draft.parent_revision_id,
        "instruction": draft.instruction,
        "target_scene_ids": list(draft.target_scene_ids),
        "candidate_source": draft.candidate_source,
        "preview_manifest_hash": draft.preview_manifest_hash,
        "preview_video_hash": draft.preview_video_hash,
        "failure_reason": draft.failure_reason,
    }


def sqlite_values(draft: ModificationDraft) -> tuple[object, ...]:
    payload = json.dumps(draft_payload(draft), sort_keys=True, separators=(",", ":"))
    return (
        draft.draft_id,
        draft.tenant_id,
        draft.job_id,
        draft.idempotency_key,
        draft.request_hash,
        draft.candidate_revision_id,
        draft.state.value,
        draft.version,
        draft.quality_run_id,
        draft.quality_job_id,
        payload,
    )


def draft_from_row(row: Mapping[str, object]) -> ModificationDraft:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, Mapping):
        payload = dict(payload)
    return ModificationDraft(
        str(row["draft_id"]),
        str(row["tenant_id"]),
        str(row["job_id"]),
        str(row["idempotency_key"]),
        str(row["request_hash"]),
        str(payload["parent_revision_id"]),
        str(row["candidate_revision_id"]),
        str(payload["instruction"]),
        tuple(payload["target_scene_ids"]),
        str(payload["candidate_source"]),
        _optional(payload["preview_manifest_hash"]),
        _optional(payload["preview_video_hash"]),
        DraftState(str(row["state"])),
        int(row["version"]),
        _optional(payload["failure_reason"]),
        _optional(row["quality_run_id"]),
        _optional(row["quality_job_id"]),
    )


def _optional(value: object) -> str | None:
    return None if value is None else str(value)
