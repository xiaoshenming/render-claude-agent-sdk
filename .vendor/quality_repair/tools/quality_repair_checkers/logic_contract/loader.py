"""Contract loading and geometry extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from libs.quality_repair.semantic_contract.geometry_facts import extract_geometry_facts


@dataclass
class GeometryEvidence:
    points: dict[str, tuple[float, float, float]]
    line_segments: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]]


def load_contract(workdir: Path) -> dict[str, Any] | None:
    for path in (workdir / "facts" / "logic_contract.json", workdir / "logic_contract_context.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            return canonical_contract(payload)
    return None


def canonical_contract(contract: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(contract)
    contracts = normalized.get("contracts")
    first_contract = contracts[0] if isinstance(contracts, list) and contracts and isinstance(contracts[0], dict) else {}
    before_validation = normalized.get("before_validation")
    issues = before_validation.get("issues") if isinstance(before_validation, dict) else None
    first_issue = issues[0] if isinstance(issues, list) and issues and isinstance(issues[0], dict) else {}
    evidence = first_issue.get("evidence") if isinstance(first_issue.get("evidence"), dict) else {}
    normalized.setdefault("contracts", contracts if isinstance(contracts, list) else [first_contract])
    _set_if_missing(normalized, "kind", first_contract.get("kind"))
    _set_if_missing(normalized, "target", first_issue.get("target") or first_contract.get("target") or first_contract.get("move_point"))
    _set_if_missing(normalized, "expected_coords", evidence.get("expected_coords") or first_contract.get("expected_coords"))
    _set_if_missing(normalized, "actual_coords", evidence.get("actual_coords"))
    _set_if_missing(normalized, "expected_length", evidence.get("reference_length") or first_contract.get("expected_length"))
    for key in ("source", "line", "points", "endpoints", "expected_degrees"):
        _set_if_missing(normalized, key, first_contract.get(key))
    return normalized


def extract_geometry(source: str, scene_name: str) -> GeometryEvidence:
    facts = extract_geometry_facts(source, scene_name=scene_name)
    return GeometryEvidence(
        points=facts.points,
        line_segments={name: segment.endpoints for name, segment in facts.line_segments.items()},
    )


def _set_if_missing(target: dict[str, Any], key: str, value: Any) -> None:
    if key not in target and value is not None:
        target[key] = value
