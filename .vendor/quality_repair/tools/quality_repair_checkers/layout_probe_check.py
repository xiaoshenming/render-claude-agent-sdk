#!/usr/bin/env python3
"""External layout probe checker wrapper for quality_repair bundles."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LAYOUT_PROBE_IMAGE = "docker-manim-worker-1:latest"
DEFAULT_LAYOUT_PROBE_CUSTOM_SERVICES = REPO_ROOT / "tools" / "solve_pre_stream_demo" / "custom_services"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_check(*, code_path: Path, workdir: Path, scene_name: str, timeout: int) -> dict[str, Any]:
    _ensure_probe_env()
    try:
        from tools.layout_mvp_replay_quality_cases import _docker_layout_probe
    except Exception as exc:  # noqa: BLE001
        return _error_payload(f"layout_probe_import_error:{exc}")
    try:
        probe = _docker_layout_probe(
            source_path=code_path,
            scene_name=scene_name,
            output_dir=workdir / "layout_probe_check",
            timeout_sec=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return _error_payload(f"layout_probe_exception:{exc}")
    return payload_from_probe(probe)


def _ensure_probe_env() -> None:
    os.environ.setdefault("VIDEO_QUALITY_REPAIR_LAB_MANIM_IMAGE", DEFAULT_LAYOUT_PROBE_IMAGE)
    os.environ.setdefault("VIDEO_QUALITY_REPAIR_LAB_CUSTOM_SERVICES_DIR", str(DEFAULT_LAYOUT_PROBE_CUSTOM_SERVICES))


def payload_from_probe(probe: dict[str, Any]) -> dict[str, Any]:
    if not probe.get("ok"):
        errors = probe.get("errors") or []
        error = ";".join(_error_text(item) for item in errors) or str(probe.get("error") or "layout_probe_not_ok")
        return _error_payload(error)
    raw_issues = [
        item
        for item in list(probe.get("top_overlaps") or []) + list(probe.get("top_bounds_violations") or [])
        if isinstance(item, dict)
    ]
    repair_issues = [item for item in raw_issues if _is_repair_blocking_issue(item)]
    issues = [
        _normalize_issue(item)
        for item in repair_issues
    ]
    return {
        "ok": True,
        "passed": not issues,
        "blocking_count": len(issues),
        "issues": issues,
        "raw": {
            "scene_name": probe.get("scene_name"),
            "estimated_duration": probe.get("estimated_duration"),
            "snapshot_count": probe.get("snapshot_count"),
            "log": probe.get("log"),
            "raw_issue_count": len(raw_issues),
            "ignored_issue_count": len(raw_issues) - len(repair_issues),
        },
    }


def _error_payload(error: str) -> dict[str, Any]:
    return {"ok": False, "passed": False, "blocking_count": -1, "issues": [], "error": error}


def _normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(issue)
    if "a" not in normalized and "b" not in normalized and isinstance(normalized.get("object"), dict):
        normalized["a"] = normalized["object"]
    for key in ("a", "b", "object", "object_a", "object_b"):
        value = normalized.get(key)
        if isinstance(value, dict):
            normalized[f"{key}_raw"] = value
            normalized[key] = _object_ref(value)
    return normalized


def _is_repair_blocking_issue(issue: dict[str, Any]) -> bool:
    category = str(issue.get("category") or issue.get("kind") or issue.get("type") or "")
    if _looks_like_formula_internal_artifact_overlap(issue):
        return False
    if category == "text_formula_overlap" and _looks_like_low_ratio_formula_stack_touch(issue):
        return False
    if category == "text_formula_overlap" and _looks_like_low_ratio_text_formula_edge_touch(issue):
        return False
    if category == "text_container_overflow" and _looks_like_highlight_rectangle_not_container(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_low_priority_near_collision(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_bbox_only_diagonal_line_label_overlap(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_formula_cancellation_line(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_axis_origin_label_overlap(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_coordinate_label_axis_overlap(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_short_label_over_area_polygon(issue):
        return False
    if category == "label_shape_overlap_risk" and _looks_like_non_blocking_radical_bar_gap(issue):
        return False
    if category == "frame_bounds_overflow" and not _has_actionable_bounds_overflow(issue):
        return False
    return True


def _looks_like_low_ratio_formula_stack_touch(issue: dict[str, Any]) -> bool:
    if _float(issue.get("ratio_of_smaller")) > 0.16:
        return False
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    if len(objects) != 2:
        return False
    if not all(str(obj.get("kind") or "") == "formula" for obj in objects):
        return False
    texts = [str(obj.get("text") or "").strip() for obj in objects]
    if not all(texts):
        return False
    return any(text.startswith("=") for text in texts)


def _looks_like_low_ratio_text_formula_edge_touch(issue: dict[str, Any]) -> bool:
    if _float(issue.get("ratio_of_smaller")) > 0.15:
        return False
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    if len(objects) != 2:
        return False
    if not all(str(obj.get("kind") or "") in {"text", "formula"} for obj in objects):
        return False
    return True


def _looks_like_formula_internal_artifact_overlap(issue: dict[str, Any]) -> bool:
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    if len(objects) < 2:
        return _looks_like_formula_internal_bounds_artifact(issue)
    if _has_parent_child_formula_pair(objects):
        return True
    rectangle = next((obj for obj in objects if str(obj.get("class") or "") == "Rectangle"), None)
    other = next((obj for obj in objects if obj is not rectangle), None)
    if rectangle and other and _is_thin_formula_artifact(rectangle) and str(other.get("kind") or "") in {"text", "formula"}:
        return True
    return False


def _looks_like_highlight_rectangle_not_container(issue: dict[str, Any]) -> bool:
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    content = next((obj for obj in objects if str(obj.get("kind") or "") in {"text", "formula"}), None)
    rectangle = next((obj for obj in objects if str(obj.get("class") or "") == "SurroundingRectangle"), None)
    if not content or not rectangle:
        return False
    if _float(issue.get("ratio_of_smaller")) <= 0.2:
        return True
    content_bbox = content.get("bbox")
    rect_bbox = rectangle.get("bbox")
    if not isinstance(content_bbox, dict) or not isinstance(rect_bbox, dict):
        return False
    content_width = _float(content_bbox.get("width"))
    content_height = _float(content_bbox.get("height"))
    rect_width = _float(rect_bbox.get("width"))
    rect_height = _float(rect_bbox.get("height"))
    if rect_width <= 0 or rect_height <= 0:
        return False
    return content_width > rect_width * 1.4 or content_height > rect_height * 1.4


def _looks_like_formula_internal_bounds_artifact(issue: dict[str, Any]) -> bool:
    obj = issue.get("object")
    if not isinstance(obj, dict):
        return False
    if _is_thin_formula_artifact(obj):
        return True
    parent_path = str(obj.get("parent_path") or "")
    path = str(obj.get("path") or "")
    return bool(parent_path and path.startswith(parent_path + ".") and str(obj.get("class") or "") == "SingleStringMathTex")


def _has_parent_child_formula_pair(objects: list[dict[str, Any]]) -> bool:
    for index, first in enumerate(objects):
        first_path = str(first.get("path") or "")
        if not first_path:
            continue
        for second in objects[index + 1 :]:
            second_path = str(second.get("path") or "")
            if not second_path:
                continue
            if not (first_path.startswith(second_path + ".") or second_path.startswith(first_path + ".")):
                continue
            classes = {str(first.get("class") or ""), str(second.get("class") or "")}
            kinds = {str(first.get("kind") or ""), str(second.get("kind") or "")}
            if {"formula"} & kinds and classes <= {"MathTex", "SingleStringMathTex", "Rectangle"}:
                return True
    return False


def _is_thin_formula_artifact(obj: dict[str, Any]) -> bool:
    if str(obj.get("class") or "") != "Rectangle":
        return False
    bbox = obj.get("bbox")
    if not isinstance(bbox, dict):
        return False
    if min(_float(bbox.get("width")), _float(bbox.get("height"))) > 0.03:
        return False
    path = str(obj.get("path") or "")
    parent_path = str(obj.get("parent_path") or "")
    return ".0." in path or bool(parent_path and path.startswith(parent_path + "."))


def _looks_like_non_blocking_radical_bar_gap(issue: dict[str, Any]) -> bool:
    metadata = issue.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("near_collision"):
        return False
    if _float(issue.get("x_overlap")) > 0 and _float(issue.get("y_overlap")) > 0:
        return False
    rectangle = next(
        (obj for obj in _issue_objects(issue) if isinstance(obj, dict) and str(obj.get("class") or "") == "Rectangle"),
        None,
    )
    if not rectangle:
        return False
    bbox = rectangle.get("bbox")
    if not isinstance(bbox, dict):
        return False
    return min(_float(bbox.get("width")), _float(bbox.get("height"))) <= 0.03


def _looks_like_low_priority_near_collision(issue: dict[str, Any]) -> bool:
    metadata = issue.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("near_collision"):
        return False
    if _float(issue.get("ratio_of_smaller")) > 0.1002:
        return False
    return _float(issue.get("x_overlap")) <= 0 or _float(issue.get("y_overlap")) <= 0


def _looks_like_bbox_only_diagonal_line_label_overlap(issue: dict[str, Any]) -> bool:
    if _float(issue.get("ratio_of_smaller")) < 0.65:
        return False
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    text_obj = next((obj for obj in objects if str(obj.get("kind") or "") in {"text", "formula"}), None)
    shape_obj = next((obj for obj in objects if str(obj.get("class") or "") in {"Line", "Arrow"}), None)
    if not text_obj or not shape_obj:
        return False
    raw_text = str(text_obj.get("text") or "").strip()
    if not (1 <= len(_compact_label_text(raw_text)) <= 8):
        return False
    text_bbox = text_obj.get("bbox")
    shape_bbox = shape_obj.get("bbox")
    if not isinstance(text_bbox, dict) or not isinstance(shape_bbox, dict):
        return False
    line_width = _float(shape_bbox.get("width"))
    line_height = _float(shape_bbox.get("height"))
    if min(line_width, line_height) < 0.35 or max(line_width, line_height) < 1.2:
        return False
    text_area = _float(text_bbox.get("width")) * _float(text_bbox.get("height"))
    line_area = line_width * line_height
    return line_area > 0 and text_area / line_area <= 0.08


def _looks_like_formula_cancellation_line(issue: dict[str, Any]) -> bool:
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    text_obj = next((obj for obj in objects if str(obj.get("kind") or "") in {"text", "formula"}), None)
    line_obj = next((obj for obj in objects if str(obj.get("class") or "") == "Line"), None)
    if not text_obj or not line_obj:
        return False
    raw_text = str(text_obj.get("text") or "")
    if not any(token in raw_text for token in ("\\frac", "sqrt", "=", "+", "-")):
        return False
    line_bbox = line_obj.get("bbox")
    text_bbox = text_obj.get("bbox")
    if not isinstance(line_bbox, dict) or not isinstance(text_bbox, dict):
        return False
    line_area = _float(line_bbox.get("width")) * _float(line_bbox.get("height"))
    text_area = _float(text_bbox.get("width")) * _float(text_bbox.get("height"))
    return text_area > 0 and line_area / text_area <= 0.25


def _looks_like_axis_origin_label_overlap(issue: dict[str, Any]) -> bool:
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    text_obj = next((obj for obj in objects if str(obj.get("kind") or "") in {"text", "formula"}), None)
    shape_obj = next((obj for obj in objects if str(obj.get("class") or "") in {"Line", "Arrow"}), None)
    if not text_obj or not shape_obj:
        return False
    if str(text_obj.get("text") or "").strip() not in {"O", "0"}:
        return False
    text_bbox = text_obj.get("bbox")
    shape_bbox = shape_obj.get("bbox")
    if not isinstance(text_bbox, dict) or not isinstance(shape_bbox, dict):
        return False
    if max(_float(text_bbox.get("width")), _float(text_bbox.get("height"))) > 0.28:
        return False
    return max(_float(shape_bbox.get("width")), _float(shape_bbox.get("height"))) >= 2.0


def _looks_like_coordinate_label_axis_overlap(issue: dict[str, Any]) -> bool:
    if _float(issue.get("ratio_of_smaller")) > 0.2:
        return False
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    text_obj = next((obj for obj in objects if str(obj.get("kind") or "") in {"text", "formula"}), None)
    shape_obj = next((obj for obj in objects if str(obj.get("class") or "") in {"Line", "Arrow"}), None)
    if not text_obj or not shape_obj:
        return False
    if not re.search(r"\(-?\d+(?:/\d+)?(?:\.\d+)?,\s*-?\d+(?:/\d+)?(?:\.\d+)?\)", str(text_obj.get("text") or "").replace(" ", "")):
        return False
    bbox = shape_obj.get("bbox")
    if not isinstance(bbox, dict):
        return False
    width = _float(bbox.get("width"))
    height = _float(bbox.get("height"))
    return min(width, height) <= 0.25 and max(width, height) >= 2.0


def _looks_like_short_label_over_area_polygon(issue: dict[str, Any]) -> bool:
    objects = [obj for obj in _issue_objects(issue) if isinstance(obj, dict)]
    text_obj = next((obj for obj in objects if str(obj.get("kind") or "") in {"text", "formula"}), None)
    polygon = next((obj for obj in objects if str(obj.get("class") or "") == "Polygon"), None)
    if not text_obj or not polygon:
        return False
    raw_text = str(text_obj.get("text") or "").strip()
    compact = raw_text.replace("_", "")
    is_short_label = 1 <= len(compact) <= 3
    is_coordinate_label = bool(re.search(r"\(-?\d+(?:/\d+)?(?:\.\d+)?,\s*-?\d+(?:/\d+)?(?:\.\d+)?\)", raw_text.replace(" ", "")))
    if not (is_short_label or is_coordinate_label):
        return False
    text_bbox = text_obj.get("bbox")
    polygon_bbox = polygon.get("bbox")
    if not isinstance(text_bbox, dict) or not isinstance(polygon_bbox, dict):
        return False
    text_area = _float(text_bbox.get("width")) * _float(text_bbox.get("height"))
    polygon_area = _float(polygon_bbox.get("width")) * _float(polygon_bbox.get("height"))
    limit = 0.10 if is_coordinate_label else 0.08
    return polygon_area > 0 and text_area / polygon_area <= limit


def _has_actionable_bounds_overflow(issue: dict[str, Any]) -> bool:
    obj = issue.get("object")
    if obj is None:
        return True
    if not isinstance(obj, dict):
        return True
    bbox = obj.get("bbox")
    if not isinstance(bbox, dict) or not bbox:
        return False
    return max(_float(issue.get("overflow_x")), _float(issue.get("overflow_y"))) >= 0.06


def _issue_objects(issue: dict[str, Any]) -> list[Any]:
    return [issue[key] for key in ("a", "b", "object", "object_a", "object_b") if key in issue]


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _compact_label_text(text: str) -> str:
    return re.sub(r"[\s_{}()，,.-]", "", text.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")))


def _object_ref(value: dict[str, Any]) -> str:
    for key in ("path", "id", "name", "text", "class"):
        raw = value.get(key)
        if raw:
            return str(raw)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _error_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("error") or item)
    return str(item)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Docker layout probe and emit CheckResult-compatible JSON.")
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    payload = run_check(code_path=args.code, workdir=args.workdir, scene_name=args.scene, timeout=args.timeout)
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
