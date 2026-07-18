"""Deterministic repairability route classification."""

from __future__ import annotations

from typing import Any, Mapping

from libs.quality_repair.schemas import (
    REPAIRABILITY_AUTO_READY,
    REPAIRABILITY_DETECT_ONLY,
    REPAIRABILITY_UNKNOWN,
    RepairabilityDecision,
)
from .constants import AUTO_READY_CONTRACT_KINDS, GEOMETRY_STRUCTURAL_CONTRACT_KINDS, SOURCE_LEVEL_CONTRACT_KINDS
from .geometry import contains_number, extract_expected_points, is_non_empty, is_sequence, parse_safe_area, within_safe_area


def classify(
    profile: str,
    logic_contract: dict[str, Any] | None,
    safe_area: dict[str, Any] | None,
) -> RepairabilityDecision:
    try:
        if profile == "layout":
            return _decision(REPAIRABILITY_AUTO_READY)
        if profile != "logic":
            return _decision(REPAIRABILITY_UNKNOWN, [f"unsupported_profile:{profile}"])
        return _classify_logic(logic_contract, safe_area)
    except Exception as exc:  # noqa: BLE001 - fail-open boundary by contract.
        return _decision(REPAIRABILITY_UNKNOWN, [f"classify_error:{exc}"])


def _classify_logic(
    logic_contract: dict[str, Any] | None,
    safe_area: dict[str, Any] | None,
) -> RepairabilityDecision:
    if logic_contract is None:
        return _decision(REPAIRABILITY_DETECT_ONLY, ["missing_contract"])
    if not isinstance(logic_contract, Mapping):
        raise TypeError("logic_contract must be a mapping")
    logic_contract = _canonical_logic_contract(logic_contract)

    kind = logic_contract.get("kind")
    if kind is None or kind == "":
        return _decision(REPAIRABILITY_DETECT_ONLY, ["missing_contract"])
    kind_text = str(kind)
    if kind_text not in AUTO_READY_CONTRACT_KINDS:
        return _decision(REPAIRABILITY_DETECT_ONLY, [f"kind_not_whitelisted:{kind_text}"])
    if not _has_expected_value(logic_contract):
        return _decision(REPAIRABILITY_DETECT_ONLY, ["no_expected_value"])
    if not within_safe_area(extract_expected_points(logic_contract), parse_safe_area(safe_area)):
        return _decision(REPAIRABILITY_DETECT_ONLY, ["expected_out_of_safe_area"])
    if _has_text_dependency(logic_contract):
        return _decision(REPAIRABILITY_UNKNOWN, ["unmodeled_text_dependency"])
    return _decision(REPAIRABILITY_AUTO_READY)


def _canonical_logic_contract(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    if contract.get("kind") and _has_expected_value(contract):
        return contract
    normalized: dict[str, Any] = dict(contract)
    first_contract = _first_mapping(contract.get("contracts"))
    before_validation = contract.get("before_validation")
    validation_issues = (
        before_validation.get("issues")
        if isinstance(before_validation, Mapping)
        else None
    )
    first_issue = _first_mapping(validation_issues)
    evidence = first_issue.get("evidence") if isinstance(first_issue.get("evidence"), Mapping) else {}
    _set_if_missing(normalized, "kind", first_contract.get("kind"))
    _set_if_missing(normalized, "target", first_issue.get("target") or first_contract.get("target") or first_contract.get("move_point"))
    _set_if_missing(normalized, "expected_coords", evidence.get("expected_coords") or first_contract.get("expected_coords"))
    _set_if_missing(normalized, "expected_length", evidence.get("reference_length") or first_contract.get("expected_length"))
    _set_if_missing(normalized, "expected_value", evidence.get("expected_value") or first_contract.get("expected_value"))
    _set_if_missing(normalized, "text", first_contract.get("text"))
    _set_if_missing(normalized, "line", first_contract.get("line"))
    _set_if_missing(normalized, "source", first_contract.get("source"))
    _set_if_missing(normalized, "points", first_contract.get("points"))
    _set_if_missing(normalized, "reference_points", first_contract.get("reference_points"))
    _set_if_missing(normalized, "endpoints", first_contract.get("endpoints"))
    _set_if_missing(normalized, "line_a", first_contract.get("line_a"))
    _set_if_missing(normalized, "line_b", first_contract.get("line_b"))
    _set_if_missing(normalized, "segment_a", first_contract.get("segment_a"))
    _set_if_missing(normalized, "segment_b", first_contract.get("segment_b"))
    _set_if_missing(normalized, "expected_degrees", first_contract.get("expected_degrees"))
    _set_if_missing(normalized, "repair_hint", first_contract.get("repair_hint") or first_issue.get("repair_hint"))
    _set_if_missing(normalized, "suggested_replacement", first_contract.get("suggested_replacement") or first_issue.get("suggested_replacement"))
    return normalized


def _first_mapping(value: Any) -> Mapping[str, Any]:
    if is_sequence(value) and value and isinstance(value[0], Mapping):
        return value[0]
    return {}


def _set_if_missing(target: dict[str, Any], key: str, value: Any) -> None:
    if key not in target and value is not None:
        target[key] = value


def _has_expected_value(contract: Mapping[str, Any]) -> bool:
    if str(contract.get("kind") or "") in SOURCE_LEVEL_CONTRACT_KINDS:
        return _has_source_level_target(contract)
    if str(contract.get("kind") or "") in GEOMETRY_STRUCTURAL_CONTRACT_KINDS:
        return _has_geometry_structural_target(contract)
    for key in ("expected_coords", "expected_length", "expected_value", "expected"):
        if key in contract and contains_number(contract[key]):
            return True
    return False


def _has_source_level_target(contract: Mapping[str, Any]) -> bool:
    if str(contract.get("kind") or "") == "no_unescaped_latex_command":
        return bool(contract.get("text") or contract.get("line"))
    return bool(contract.get("text") or contract.get("texts"))


def _has_geometry_structural_target(contract: Mapping[str, Any]) -> bool:
    kind = str(contract.get("kind") or "")
    if kind == "point_on_line":
        return bool(contract.get("target") and contract.get("line"))
    if kind == "reflection_point":
        return bool(contract.get("target") and contract.get("source") and contract.get("line"))
    if kind == "angle_measure":
        return bool(contract.get("points") and contract.get("expected_degrees") is not None)
    if kind == "line_endpoint_match":
        return bool(contract.get("target") and contract.get("endpoints"))
    if kind == "foot_point":
        return bool(contract.get("target") and contract.get("source") and contract.get("line"))
    if kind == "line_intersection":
        return bool(contract.get("target") and contract.get("line_a") and contract.get("line_b"))
    if kind == "points_collinear":
        return bool(contract.get("points"))
    if kind == "line_perpendicular":
        return bool(contract.get("line_a") and contract.get("line_b"))
    if kind == "angle_equals_degrees":
        return bool(contract.get("points") and contract.get("expected_degrees") is not None)
    if kind == "angle_equals_angle":
        return bool(contract.get("points") and contract.get("reference_points"))
    if kind == "length_equals_length":
        return bool(contract.get("segment_a") and contract.get("segment_b"))
    return False


def _has_text_dependency(contract: Mapping[str, Any]) -> bool:
    return any(is_non_empty(contract.get(key)) for key in ("text_dependency", "voiceover_refs"))


def _decision(
    classification: str,
    reasons: list[str] | None = None,
) -> RepairabilityDecision:
    return RepairabilityDecision(classification=classification, reasons=list(reasons or []))
