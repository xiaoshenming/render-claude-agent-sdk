"""极简主管线与冻结 V3 质量模块之间的 fail-open 接口。"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.quality_platform.retention import persist_quality_event
from app.quality_platform.v3_runner import run_v3_existing_code


@dataclass(frozen=True, slots=True)
class MinimalQualityArtifact:
    code: str
    video_bytes: bytes
    video_path: str
    evidence: dict[str, Any]


async def run_minimal_quality_platform(
    worker: Any,
    *,
    task_data: dict[str, Any],
    code: str,
    video_bytes: bytes,
    video_path: str,
    prompt: str,
) -> MinimalQualityArtifact:
    """运行完整 V3；模块异常时保留 Render Agent 的可播放产物。"""
    if not _enabled(task_data):
        evidence = _evidence("disabled", "DISABLED", False, None)
        await _persist(task_data, evidence)
        return MinimalQualityArtifact(code, video_bytes, video_path, evidence)
    run_root = (
        Path(worker.manim_media_root)
        / f"job_{task_data['job_id']}"
        / "manim_quality_platform"
        / _run_id(task_data)
    )
    try:
        result = await asyncio.to_thread(
            run_v3_existing_code,
            job_id=str(task_data["job_id"]),
            candidate_code=code,
            problem_text=_problem(task_data, prompt),
            expected_solution=_expected(task_data),
            output_dir=run_root,
        )
        evidence = _evidence(
            result.status,
            "ACCEPT" if not result.fail_open_used else "ERROR",
            result.fail_open_used,
            result.evidence,
            manifest_path=str(result.result_path or ""),
        )
        if result.fail_open_used or result.final_video_path is None:
            artifact = MinimalQualityArtifact(code, video_bytes, video_path, evidence)
        else:
            artifact = MinimalQualityArtifact(
                result.selected_code,
                result.final_video_path.read_bytes(),
                str(result.final_video_path),
                evidence,
            )
    except Exception as exc:  # noqa: BLE001 - 已渲染视频必须继续归档。
        evidence = _evidence(
            "orchestrator_fail_open",
            "ERROR",
            True,
            None,
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
        artifact = MinimalQualityArtifact(code, video_bytes, video_path, evidence)
    await _persist(task_data, evidence)
    return artifact


async def _persist(task_data: dict[str, Any], evidence: dict[str, Any]) -> None:
    from app.workers.task_dispatcher import log_render_quality_event

    await persist_quality_event(log_render_quality_event, task_data, evidence)
    task_data["_pre_archive_quality_platform"] = evidence


def _evidence(
    status: str,
    decision: str,
    fail_open: bool,
    payload: dict[str, Any] | None,
    *,
    manifest_path: str = "",
    error: str = "",
) -> dict[str, Any]:
    source = payload or {}
    return {
        "schema_version": "mathpi.render-quality-platform-entrypoint.v3",
        "source_head": "manim_quality_complete_handoff_20260715_v3",
        "model": settings.MANIM_QUALITY_MODEL,
        "status": status,
        "decision": decision,
        "fail_open_used": fail_open,
        "orchestrator_execute_count": 1,
        "manifest_path": manifest_path,
        "logic": source.get("logic"),
        "layout": source.get("layout"),
        "elapsed_ms": source.get("elapsed_ms"),
        "error": error or source.get("bridge_error", ""),
    }


def _enabled(task: dict[str, Any]) -> bool:
    override = task.get("_agent_manim_quality_platform_enabled")
    if override is not None:
        return str(override).lower() in {"1", "true", "yes", "on"}
    return bool(settings.MANIM_QUALITY_PLATFORM_PRE_ARCHIVE_ENABLED)


def _run_id(task: dict[str, Any]) -> str:
    value = str(task.get("attempt_id") or uuid.uuid4().hex)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in value)
    return f"mathpi-{safe[:80]}"


def _problem(task: dict[str, Any], prompt: str) -> str:
    return str(
        task.get("original_problem")
        or task.get("knowledge_point")
        or task.get("description")
        or prompt
    )


def _expected(task: dict[str, Any]) -> str:
    return str(
        task.get("expected_solution")
        or task.get("solution")
        or task.get("answer")
        or ""
    )


__all__ = ["MinimalQualityArtifact", "run_minimal_quality_platform"]
