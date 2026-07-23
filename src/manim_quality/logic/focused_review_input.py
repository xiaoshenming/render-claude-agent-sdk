"""Build bounded, scene-focused facts for the Logic Reviewer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from manim_quality.contracts._json_values import thaw_json_object

from .evidence import LogicEvidence
from .review_digest import build_review_digest

FOCUSED_SCHEMA_VERSION = "manim-quality.logic-focused-review.v1"
_MAX_ITEMS = 24


def build_focused_review_input(
    evidence: LogicEvidence,
    candidate_code: str,
) -> dict[str, object]:
    """Restore focused V3 excerpts and partition line-bound facts by Scene."""
    digest = build_review_digest(evidence, candidate_code).to_prompt_dict()
    engine = thaw_json_object(evidence.engine_evidence)
    scenes = digest["scene_index"]
    packets = [
        _scene_packet(scene, digest, engine)
        for scene in scenes
        if isinstance(scene, Mapping)
    ]
    return {
        "schema_version": FOCUSED_SCHEMA_VERSION,
        "problem": digest["problem"],
        "planning": digest["planning"],
        "expected_answer": digest["expected_answer"],
        "scene_packets": packets,
        "unlocated_claims": _without_line(digest["visible_math_claims"]),
        "input_policy": {
            "external_diagnosis_included": False,
            "repair_hints_included": False,
            "historical_verdicts_included": False,
            "candidate_readable_on_demand": True,
            "packet_scope": "scene",
        },
    }


def _scene_packet(
    scene: Mapping[str, object],
    digest: Mapping[str, object],
    engine: Mapping[str, object],
) -> dict[str, object]:
    start = int(scene["line_start"])
    end = int(scene["line_end"])
    return {
        "scene_id": scene["scene_id"],
        "line_start": start,
        "line_end": end,
        "visible_math_claims": _within(
            digest["visible_math_claims"], start, end
        ),
        "deterministic_logic_facts": _within(
            digest["deterministic_logic_facts"], start, end
        ),
        "numeric_vectors": _within(digest["numeric_vectors"], start, end),
        "constructions": _within(digest["constructions"], start, end),
        "focused_code_excerpts": _within(
            engine.get("focused_code_excerpts"), start, end
        ),
        "helper_method_excerpts": _relevant_helpers(
            engine.get("helper_method_excerpts"), start, end
        ),
    }


def _within(value: object, start: int, end: int) -> list[object]:
    return [
        item
        for item in _items(value)
        if (line := _line(item)) is not None and start <= line <= end
    ][:_MAX_ITEMS]


def _without_line(value: object) -> list[object]:
    return [item for item in _items(value) if _line(item) is None][:_MAX_ITEMS]


def _relevant_helpers(value: object, start: int, end: int) -> list[object]:
    presentation_only = {
        "label_near_point",
        "make_card",
        "make_text",
        "make_title",
    }
    return [
        item
        for item in _within(value, start, end)
        if not (
            isinstance(item, Mapping)
            and item.get("method_name") in presentation_only
        )
    ]


def _items(value: object) -> Sequence[object]:
    if isinstance(value, Mapping):
        return tuple(
            {"fact_id": str(key), "value": item} for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _line(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None
    for key in ("line", "line_start", "lineno"):
        item = value.get(key)
        if isinstance(item, int) and item > 0:
            return item
    nested = value.get("source")
    return _line(nested) if isinstance(nested, Mapping) else None
