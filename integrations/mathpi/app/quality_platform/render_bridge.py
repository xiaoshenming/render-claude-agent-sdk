"""MathPi fail-open adapter around the frozen V3 existing-code entrypoint."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Mapping

from app.core.config import settings

from .v3_runner import run_v3_existing_code


async def run_before_renderable_archive(
    runtime: Any, state: Mapping[str, Any], code: str
) -> tuple[str, dict[str, Any]]:
    if not _enabled(runtime.task_data):
        return code, _disabled_evidence()
    task = runtime.task_data
    metadata = state.get("metadata") or {}
    try:
        result = await asyncio.to_thread(
            run_v3_existing_code,
            job_id=_native_job_id(runtime.job_id, task),
            candidate_code=code,
            problem_text=_first_text(
                task,
                "description",
                "knowledge_point",
                "problem_text",
                default=str(runtime.prompt or ""),
            ),
            expected_solution=_first_text(
                task, "expected_solution", "solution", "answer"
            ),
            output_dir=_artifact_root(runtime, metadata) / _run_id(task),
        )
    except Exception as error:  # noqa: BLE001 - playable code must survive.
        return code, _failure_evidence(error)
    return result.selected_code, {
        "schema_version": "mathpi.render-quality-platform-entrypoint.v3",
        "source_head": "manim_quality_complete_handoff_20260715_v3",
        "status": result.status,
        "decision": "ACCEPT" if not result.fail_open_used else "ERROR",
        "fail_open_used": result.fail_open_used,
        "orchestrator_execute_count": 1,
        "manifest_path": str(result.result_path or ""),
        "logic": result.evidence.get("logic"),
        "layout": result.evidence.get("layout"),
        "elapsed_ms": result.evidence.get("elapsed_ms"),
        "error": result.evidence.get("bridge_error", ""),
    }


def _failure_evidence(error: Exception) -> dict[str, Any]:
    return {
        "schema_version": "mathpi.render-quality-platform-entrypoint.v3",
        "source_head": "manim_quality_complete_handoff_20260715_v3",
        "status": "orchestrator_fail_open",
        "decision": "ERROR",
        "fail_open_used": True,
        "orchestrator_execute_count": 1,
        "manifest_path": "",
        "logic": None,
        "layout": None,
        "elapsed_ms": None,
        "error": f"{type(error).__name__}: {error}"[:1000],
    }


def _disabled_evidence() -> dict[str, Any]:
    evidence = _failure_evidence(RuntimeError("disabled"))
    evidence.update(
        status="disabled", decision="DISABLED", error="", orchestrator_execute_count=0
    )
    return evidence


def _enabled(task: Mapping[str, Any]) -> bool:
    for name in ("_agent_manim_quality_platform_enabled", "_manim_quality_platform_enabled"):
        if name in task:
            return str(task.get(name)).lower() in {"1", "true", "yes", "on"}
    return bool(settings.MANIM_QUALITY_PLATFORM_PRE_ARCHIVE_ENABLED)


def _artifact_root(runtime: Any, metadata: Mapping[str, Any]) -> Path:
    base = Path(
        str(metadata.get("script_path") or getattr(runtime.worker, "cache_dir", "render_cache"))
    )
    if base.suffix:
        base = base.parent
    return base / "manim_quality_platform" / "v3"


def _run_id(task: Mapping[str, Any]) -> str:
    value = _first_text(task, "attempt_id", "_attempt_id", "request_id") or uuid.uuid4().hex
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in value)
    return "mathpi-" + safe[:80]


def _native_job_id(job_id: Any, task: Mapping[str, Any]) -> str:
    retry_count = int(task.get("retry_count") or 0)
    return str(job_id) if retry_count <= 0 else f"{job_id}--retry-{retry_count}"


def _first_text(values: Mapping[str, Any], *names: str, default: str = "") -> str:
    return next((str(values.get(name)).strip() for name in names if values.get(name)), default)


__all__ = ["run_before_renderable_archive"]
