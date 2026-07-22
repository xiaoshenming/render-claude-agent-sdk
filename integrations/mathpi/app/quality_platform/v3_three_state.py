"""把 V3 全视频 A/B/C 证据上传并索引到管理后台。"""

from __future__ import annotations

import difflib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.workers.quality_cases.persist import persist_quality_case
from app.workers.quality_cases.schemas import QualityCaseManifest, StageInfo

CASE_ID = "__v3_three_state__"
SCENE_NAME = "V3 全视频三态"


async def persist_v3_three_state(
    *,
    job_id: str,
    aspect_ratio: str,
    original_code: str,
    original_video_path: str,
    result_path: Path | None,
) -> dict[str, Any] | None:
    """上传 A 原始、B 逻辑后、C 布局后；任何缺件都降级记录。"""
    if result_path is None or not result_path.is_file():
        return None
    run_dir = result_path.parent
    payload = _read_json(result_path)
    case_dir = run_dir / "three_state_evidence"
    case_dir.mkdir(parents=True, exist_ok=True)
    baseline_code = case_dir / "baseline.py"
    baseline_code.write_text(original_code, encoding="utf-8")

    logic_payload = _dict(payload.get("logic"))
    layout_payload = _dict(payload.get("layout"))
    logic_code = _existing_path(logic_payload.get("candidate_path")) or baseline_code
    layout_code = _existing_path(layout_payload.get("candidate_path")) or logic_code
    baseline_video = _existing_path(original_video_path) or _render_video(run_dir / "render_baseline")
    logic_video = _render_video(run_dir / "render_after_logic") or baseline_video
    layout_video = _render_video(run_dir / "render_after_layout") or logic_video

    logic_diff = _write_diff(case_dir / "logic.diff", baseline_code, logic_code)
    layout_diff = _write_diff(case_dir / "layout.diff", logic_code, layout_code)
    before_count = _integer(layout_payload.get("before_blocking"))
    after_count = _integer(layout_payload.get("after_blocking"))
    manifest = QualityCaseManifest(
        case_id=CASE_ID,
        job_id=job_id,
        scene_name=SCENE_NAME,
        pipeline="v3_minimal",
        case_type="v3_three_state",
        aspect_ratio=aspect_ratio,
        created_at=datetime.now().isoformat(timespec="seconds"),
        case_status="captured" if baseline_video and layout_video else "partial",
        case_dir=str(case_dir),
        baseline=StageInfo(
            status="available" if baseline_video else "missing",
            code_path=str(baseline_code),
            video_path=str(baseline_video) if baseline_video else None,
            source="render_agent_initial",
        ),
        logic_fixed=StageInfo(
            status=_logic_status(str(logic_payload.get("status") or "")),
            code_path=str(logic_code),
            video_path=str(logic_video) if logic_video else None,
            diff_path=str(logic_diff) if logic_diff else None,
            repair_method="claude_agent_sdk_v3",
            repair_source="logic_agent",
        ),
        layout_fixed=StageInfo(
            status=_layout_status(str(layout_payload.get("status") or "")),
            code_path=str(layout_code),
            video_path=str(layout_video) if layout_video else None,
            diff_path=str(layout_diff) if layout_diff else None,
            repair_method="claude_agent_sdk_v3",
            repair_source="overlap_agent",
            before_overlap_count=before_count,
            after_overlap_count=after_count,
        ),
        notes=["V3 新版整视频三态；状态缺失时复用上一态视频，不阻断归档。"],
    )
    return await persist_quality_case(case_dir=case_dir, manifest=manifest)


def _render_video(render_dir: Path) -> Path | None:
    payload = _read_json(render_dir / "render.json")
    return _existing_path(payload.get("video_path"))


def _write_diff(dest: Path, before: Path, after: Path) -> Path | None:
    if before.resolve() == after.resolve():
        return None
    try:
        diff = difflib.unified_diff(
            before.read_text(encoding="utf-8").splitlines(keepends=True),
            after.read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile=before.name,
            tofile=after.name,
        )
        dest.write_text("".join(diff), encoding="utf-8")
        return dest if dest.stat().st_size else None
    except OSError:
        return None


def _logic_status(status: str) -> str:
    if status == "candidate_ready":
        return "repaired"
    if status in {"review_pass", "review_record_only"}:
        return "not_triggered"
    return "repair_failed"


def _layout_status(status: str) -> str:
    if status.startswith("accepted") or status in {
        "candidate_recheck_required",
        "residual_candidate_recheck_required",
        "vendor_clean_recheck_required",
    }:
        return "repaired"
    if status == "clean":
        return "not_triggered"
    return "repair_failed"


def _existing_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_file() and path.stat().st_size > 0 else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["persist_v3_three_state"]
