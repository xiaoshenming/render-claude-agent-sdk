"""quality_repair.contract.assert_contract — 世界模型相等断言（设计 §七）。

checker 判定用到的对象集合必须被 facts/layout_context.json 或根 layout_context.json 覆盖；不一致时
上游应直接判 REPAIR_UNCHANGED，agent 不上场。本函数只做布尔判定 + reasons，
绝不抛异常（含兜底 except，任何解析异常都转成结构化失败原因）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..schemas import PROFILE_LOGIC, CheckResult, read_json

_CHECKER_PAIR_KEYS = ("a", "object_a", "b", "object_b")
_CHECKER_LIST_KEY = "objects"
_FACTS_OBJECT_KEYS = ("objects", "active_objects", "bboxes", "active_visible_objects")
_FACTS_ISSUE_KEYS = ("top_blocking_issues", "collisions", "blocking_pairs", "issues")
_ELEMENT_ID_FIELDS = ("id", "name", "path")
_SOURCE_LEVEL_CONTRACT_KINDS = {
    "source_contains",
    "source_not_contains",
    "must_contain",
    "must_not_contain",
    "forbid_text",
    "no_unescaped_latex_command",
}
_GEOMETRY_STRUCTURAL_CONTRACT_KINDS = {
    "point_on_line",
    "reflection_point",
    "angle_measure",
    "line_endpoint_match",
    "foot_point",
    "line_intersection",
    "points_collinear",
    "line_perpendicular",
    "angle_equals_degrees",
    "angle_equals_angle",
    "length_equals_length",
}


def assert_contract(workdir: Path, check: CheckResult, *, profile: str = "layout") -> tuple[bool, list[str]]:
    """checker 对象集合 ⊆ facts 对象集合 → (True, [])，否则给出结构化原因。"""
    if profile == PROFILE_LOGIC:
        return _assert_logic_contract(workdir)
    try:
        checker_objects = _collect_checker_objects(check)
        facts_objects, found = _collect_facts_objects(workdir)
        if not found:
            return False, ["facts_unavailable"]
        missing = sorted(name for name in checker_objects if name not in facts_objects)
        if missing:
            return False, [f"missing_object:{name}" for name in missing]
        return True, []
    except Exception as exc:  # noqa: BLE001 - 层边界：绝不上抛
        return False, [f"contract_assert_error:{exc}"]


def _assert_logic_contract(workdir: Path) -> tuple[bool, list[str]]:
    try:
        data = read_json(workdir / "facts" / "logic_contract.json")
    except (OSError, ValueError):
        return False, ["logic_contract_unavailable"]
    if not isinstance(data, dict):
        return False, ["logic_contract_unavailable"]

    reasons: list[str] = []
    if not data.get("kind"):
        reasons.append("logic_contract_missing_kind")
    if not _has_expected_value(data):
        reasons.append("logic_contract_missing_expected")
    try:
        source_region = (workdir / "facts" / "source_region.md").read_text(encoding="utf-8")
    except OSError:
        source_region = ""
    if not source_region.strip():
        reasons.append("source_region_unavailable")
    return not reasons, reasons


def _collect_checker_objects(check: CheckResult) -> set[str]:
    names: set[str] = set()
    for issue in check.issues:
        if not isinstance(issue, dict):
            continue
        for key in _CHECKER_PAIR_KEYS:
            value = issue.get(key)
            if value is not None:
                names.add(str(value))
        objects = issue.get(_CHECKER_LIST_KEY)
        if isinstance(objects, list):
            names.update(str(v) for v in objects)
    return names


def _collect_facts_objects(workdir: Path) -> tuple[set[str], bool]:
    facts_path = workdir / "facts" / "layout_context.json"
    try:
        data = read_json(facts_path)
    except (OSError, ValueError):
        try:
            data = read_json(workdir / "layout_context.json")
        except (OSError, ValueError):
            return set(), False
    if not isinstance(data, dict):
        return set(), False
    facts_objects: set[str] = set()
    found = False
    for key in _FACTS_OBJECT_KEYS:
        container = data.get(key)
        if isinstance(container, list):
            facts_objects.update(_element_name(item) for item in container)
            found = True
        if isinstance(container, dict):
            facts_objects.update(str(k) for k in container.keys())
            found = True
    for key in _FACTS_ISSUE_KEYS:
        issues = data.get(key)
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            for pair_key in _CHECKER_PAIR_KEYS:
                value = issue.get(pair_key)
                if value is None:
                    continue
                facts_objects.add(_element_name(value))
                found = True
            for raw_key in ("a_raw", "b_raw"):
                value = issue.get(raw_key)
                if value is None:
                    continue
                facts_objects.add(_element_name(value))
                found = True
    return facts_objects, found


def _element_name(item: Any) -> str:
    if isinstance(item, dict):
        for field in _ELEMENT_ID_FIELDS:
            if field in item:
                return str(item[field])
        return str(item)
    return str(item)


def _has_expected_value(data: dict[str, Any]) -> bool:
    if str(data.get("kind") or "") in _SOURCE_LEVEL_CONTRACT_KINDS:
        return _has_source_level_target(data)
    if str(data.get("kind") or "") in _GEOMETRY_STRUCTURAL_CONTRACT_KINDS:
        return _has_geometry_structural_target(data)
    for key in ("expected_coords", "expected_length", "expected_value", "expected"):
        if key in data and _contains_number(data[key]):
            return True
    return False


def _has_source_level_target(data: dict[str, Any]) -> bool:
    if str(data.get("kind") or "") == "no_unescaped_latex_command":
        return bool(data.get("text") or data.get("line"))
    return bool(data.get("text") or data.get("texts"))


def _has_geometry_structural_target(data: dict[str, Any]) -> bool:
    kind = str(data.get("kind") or "")
    if kind == "point_on_line":
        return bool(data.get("target") and data.get("line"))
    if kind == "reflection_point":
        return bool(data.get("target") and data.get("source") and data.get("line"))
    if kind == "angle_measure":
        return bool(data.get("points") and data.get("expected_degrees") is not None)
    if kind == "line_endpoint_match":
        return bool(data.get("target") and data.get("endpoints"))
    if kind == "foot_point":
        return bool(data.get("target") and data.get("source") and data.get("line"))
    if kind == "line_intersection":
        return bool(data.get("target") and data.get("line_a") and data.get("line_b"))
    if kind == "points_collinear":
        return bool(data.get("points"))
    if kind == "line_perpendicular":
        return bool(data.get("line_a") and data.get("line_b"))
    if kind == "angle_equals_degrees":
        return bool(data.get("points") and data.get("expected_degrees") is not None)
    if kind == "angle_equals_angle":
        return bool(data.get("points") and data.get("reference_points"))
    if kind == "length_equals_length":
        return bool(data.get("segment_a") and data.get("segment_b"))
    return False


def _contains_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_contains_number(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_number(item) for item in value)
    return False
