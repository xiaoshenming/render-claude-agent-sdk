"""Archive manifest upload and quality-event persistence orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from .retention import persist_quality_event

logger = logging.getLogger("render")


async def retain_quality_archive_evidence(
    *,
    job_id: str,
    task_data: Mapping[str, Any],
    evidence: dict[str, Any],
    upload_file: Callable[..., Awaitable[str]],
    log_event: Callable[..., Awaitable[Any]],
    retry_count: int,
) -> bool:
    """Best-effort upload of the manifest followed by the durable DB event."""
    manifest_url = await _upload_manifest(
        job_id=job_id,
        evidence=evidence,
        upload_file=upload_file,
        retry_count=retry_count,
    )
    evidence["manifest_url"] = manifest_url or ""
    return await persist_quality_event(
        log_event,
        task_data,
        evidence,
        manifest_url=manifest_url or "",
    )


async def _upload_manifest(
    *,
    job_id: str,
    evidence: Mapping[str, Any],
    upload_file: Callable[..., Awaitable[str]],
    retry_count: int,
) -> str | None:
    manifest_path = Path(str(evidence.get("manifest_path") or ""))
    if not manifest_path.is_file():
        return None
    attempt_id = manifest_path.parent.name
    key = (
        f"quality-platform/{job_id}/pre-archive/"
        f"retry-{retry_count}/{attempt_id}/manifest.json"
    )
    try:
        url = await upload_file(
            key,
            manifest_path.read_bytes(),
            content_type="application/json; charset=utf-8",
        )
        return str(url) if str(url).startswith("http") else None
    except Exception as exc:  # noqa: BLE001 - evidence upload is diagnostic only.
        logger.warning(
            "[QUALITY-PLATFORM] manifest upload failed: job=%s error=%s",
            job_id,
            exc,
        )
        return None
