"""Platform impact classification for raw overlap detector observations."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

POLICY_VERSION = "overlap-impact.v1"
_AREA_SHAPES = frozenset(
    {"Circle", "Ellipse", "Polygon", "Rectangle", "RoundedRectangle", "Square"}
)
_CONTENT_KINDS = frozenset({"formula", "text"})


class ImpactClassifyingChecker:
    """Downgrade proven design containment while preserving raw evidence."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def run_check(self, code_path: Path, workdir: Path) -> Any:
        result = self._delegate.run_check(code_path, workdir)
        if not result.ok or result.blocking_count < 0:
            return result
        blocking, warnings = _classify(list(result.issues))
        raw = dict(getattr(result, "raw", {}) or {})
        raw.update(
            {
                "platform_policy_version": POLICY_VERSION,
                "platform_raw_blocking_count": result.blocking_count,
                "platform_warning_count": len(warnings),
                "platform_warnings": warnings,
            }
        )
        _write_evidence(workdir, result.blocking_count, blocking, warnings)
        return replace(
            result,
            passed=not blocking,
            blocking_count=len(blocking),
            issues=blocking,
            raw=raw,
        )


def _classify(issues: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    blocking: list[dict] = []
    warnings: list[dict] = []
    for issue in issues:
        if _is_centered_contained_label(issue):
            warnings.append(
                {
                    "reason": "ambiguous_centered_shape_label",
                    "release_policy": "record_only",
                    "issue": issue,
                }
            )
        else:
            blocking.append(issue)
    return blocking, warnings


def _is_centered_contained_label(issue: dict[str, Any]) -> bool:
    category = str(issue.get("category") or issue.get("kind") or "")
    if category != "label_shape_overlap_risk":
        return False
    objects = _issue_objects(issue)
    shape = next(
        (item for item in objects if str(item.get("class") or "") in _AREA_SHAPES),
        None,
    )
    content = next(
        (item for item in objects if str(item.get("kind") or "") in _CONTENT_KINDS),
        None,
    )
    if shape is None or content is None or shape is content:
        return False
    if not _is_short_label(content):
        return False
    shape_box = _bbox(shape)
    content_box = _bbox(content)
    if shape_box is None or content_box is None:
        return False
    return _contained(content_box, shape_box) and _centered(content_box, shape_box)


def _issue_objects(issue: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for key in ("a_raw", "b_raw", "object_raw", "a", "b", "object"):
        value = issue.get(key)
        if isinstance(value, dict) and value not in values:
            values.append(value)
    return values


def _bbox(obj: dict[str, Any]) -> dict[str, float] | None:
    raw = obj.get("bbox")
    if not isinstance(raw, dict):
        return None
    keys = ("left", "right", "top", "bottom", "width", "height", "center_x", "center_y")
    try:
        box = {key: float(raw[key]) for key in keys}
    except (KeyError, TypeError, ValueError):
        return None
    if box["width"] <= 0 or box["height"] <= 0:
        return None
    return box


def _contained(content: dict[str, float], shape: dict[str, float]) -> bool:
    epsilon = 1e-6
    area_ratio = (content["width"] * content["height"]) / (
        shape["width"] * shape["height"]
    )
    return (
        area_ratio <= 0.35
        and content["left"] >= shape["left"] - epsilon
        and content["right"] <= shape["right"] + epsilon
        and content["bottom"] >= shape["bottom"] - epsilon
        and content["top"] <= shape["top"] + epsilon
    )


def _centered(content: dict[str, float], shape: dict[str, float]) -> bool:
    x_tolerance = max(0.02, shape["width"] * 0.01)
    y_tolerance = max(0.02, shape["height"] * 0.01)
    return (
        abs(content["center_x"] - shape["center_x"]) <= x_tolerance
        and abs(content["center_y"] - shape["center_y"]) <= y_tolerance
    )


def _is_short_label(content: dict[str, Any]) -> bool:
    text = "".join(str(content.get("text") or "").split())
    return 1 <= len(text) <= 8


def _write_evidence(
    workdir: Path,
    raw_count: int,
    blocking: list[dict],
    warnings: list[dict],
) -> None:
    payload = {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        "raw_blocking_count": raw_count,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "warnings": warnings,
    }
    path = workdir / "platform_overlap_classification.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
