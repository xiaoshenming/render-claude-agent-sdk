"""Normalize input contracts and layout contexts for workdir assembly."""

from __future__ import annotations

from typing import Any

COLLISION_KEYS = ("collisions", "blocking_pairs", "issues")
LOGIC_ISSUE_KEYS = ("issues", "items", "mismatches", "contracts")
FACT_OBJECT_KEYS = ("objects", "active_objects", "bboxes")


def _normalize_layout_context(layout_ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    if layout_ctx is None:
        return None
    normalized = dict(layout_ctx)
    active_objects = normalized.get("active_visible_objects")
    if isinstance(active_objects, list):
        if not any(isinstance(normalized.get(key), (list, dict)) for key in FACT_OBJECT_KEYS):
            normalized["objects"] = active_objects
        normalized.setdefault("active_objects", active_objects)
    top_issues = normalized.get("top_blocking_issues")
    if isinstance(top_issues, list) and not any(isinstance(normalized.get(key), list) for key in COLLISION_KEYS):
        normalized["collisions"] = top_issues
    return normalized


def _normalize_logic_contract(logic_contract: dict[str, Any] | None) -> dict[str, Any] | None:
    if logic_contract is None:
        return None
    normalized = dict(logic_contract)
    contracts = normalized.get("contracts")
    first_contract = contracts[0] if isinstance(contracts, list) and contracts and isinstance(contracts[0], dict) else {}
    before_validation = normalized.get("before_validation")
    validation_issues = before_validation.get("issues", []) if isinstance(before_validation, dict) else []
    first_issue = validation_issues[0] if isinstance(validation_issues, list) and validation_issues and isinstance(validation_issues[0], dict) else {}
    evidence = first_issue.get("evidence") if isinstance(first_issue.get("evidence"), dict) else {}

    if "issues" not in normalized and isinstance(validation_issues, list):
        normalized["issues"] = validation_issues
    _set_if_missing(normalized, "kind", first_contract.get("kind"))
    _set_if_missing(normalized, "contract_kind", first_contract.get("kind"))
    _set_if_missing(normalized, "target", first_issue.get("target") or first_contract.get("target") or first_contract.get("move_point"))
    _set_if_missing(normalized, "expected_coords", evidence.get("expected_coords") or first_contract.get("expected_coords"))
    _set_if_missing(normalized, "actual_coords", evidence.get("actual_coords"))
    _set_if_missing(normalized, "expected_length", evidence.get("reference_length") or first_contract.get("expected_length"))
    _set_if_missing(normalized, "actual_length", evidence.get("actual_length"))
    _set_if_missing(normalized, "expected_value", evidence.get("expected_value") or first_contract.get("expected_value"))
    for key in ("text", "line", "source", "points", "endpoints", "expected_degrees"):
        _set_if_missing(normalized, key, first_contract.get(key))
    _set_if_missing(normalized, "repair_hint", first_contract.get("repair_hint") or first_issue.get("repair_hint"))
    _set_if_missing(normalized, "suggested_replacement", first_contract.get("suggested_replacement") or first_issue.get("suggested_replacement"))
    return normalized


def _set_if_missing(target: dict[str, Any], key: str, value: Any) -> None:
    if key not in target and value is not None:
        target[key] = value


def _find_list_field(data: dict[str, Any] | None, keys: tuple[str, ...]) -> list[Any]:
    if not data:
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []
