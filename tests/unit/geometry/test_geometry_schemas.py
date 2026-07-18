import math

import pytest

from manim_quality.geometry.schemas import (
    GeometryFact,
    GeometrySnapshot,
    parse_geometry_fact,
    parse_geometry_snapshot,
)

CODE_HASH = "sha256:" + "a" * 64
SNAPSHOT_HASH = "sha256:" + "b" * 64


def source(line: int = 12) -> dict[str, object]:
    return {
        "scene_id": "Solution",
        "line_start": line,
        "line_end": line,
        "excerpt": "line_ab = Line(A, B)",
    }


def snapshot_payload() -> dict[str, object]:
    return {
        "schema_version": "manim-quality.geometry-snapshot.v1",
        "code_hash": CODE_HASH,
        "scene_id": "Solution",
        "checkpoint_id": "final-visible",
        "provenance": "runtime_checkpoint",
        "objects": [
            {
                "object_id": "line_ab",
                "kind": "line",
                "status": "known",
                "reason_code": None,
                "state": {
                    "start": [-2, 0, 0],
                    "end": [2, 0, 0],
                    "start_ref": "A",
                    "end_ref": "B",
                },
                "source": source(),
            },
            {
                "object_id": "moving_point",
                "kind": "point",
                "status": "unknown",
                "reason_code": "dynamic_value",
                "state": {},
                "source": source(20),
            },
        ],
    }


def test_snapshot_parses_into_immutable_objects_and_stable_hash() -> None:
    snapshot = parse_geometry_snapshot(snapshot_payload())

    assert isinstance(snapshot, GeometrySnapshot)
    assert snapshot.object("line_ab").state["start"] == (-2, 0, 0)
    assert snapshot.object("moving_point").status.value == "unknown"
    assert snapshot.snapshot_hash == snapshot.snapshot_hash

    with pytest.raises(TypeError):
        snapshot.object("line_ab").state["start"] = (0, 0, 0)  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update(extra=True), "fields"),
        (
            lambda data: data["objects"].append(data["objects"][0]),  # type: ignore[union-attr,index]
            "duplicate",
        ),
        (
            lambda data: data["objects"][0].update(replacement="Line(A, C)"),  # type: ignore[index,union-attr]
            "fields",
        ),
        (
            lambda data: data["objects"][0]["state"].update(expected_value=90),  # type: ignore[index,union-attr]
            "forbidden",
        ),
        (
            lambda data: data["objects"][0]["state"]["start"].__setitem__(0, math.nan),  # type: ignore[index,union-attr]
            "finite",
        ),
        (
            lambda data: data["objects"][1].update(status="unknown", reason_code=None),  # type: ignore[index,union-attr]
            "reason_code",
        ),
    ],
)
def test_snapshot_rejects_unsafe_or_ambiguous_payloads(mutate, message: str) -> None:
    payload = snapshot_payload()
    mutate(payload)

    with pytest.raises((TypeError, ValueError), match=message):
        parse_geometry_snapshot(payload)


@pytest.mark.parametrize(
    "state",
    [
        {"diagnosis": "wrong endpoint"},
        {"start": [0, 0], "end": [1, 0], "repair_hint": "move it"},
        {"start": [0], "end": [1]},
    ],
)
def test_known_object_state_must_match_its_kind_contract(state) -> None:
    payload = snapshot_payload()
    payload["objects"][0]["state"] = state  # type: ignore[index]

    with pytest.raises(ValueError):
        parse_geometry_snapshot(payload)


def fact_payload(*, status: str = "known") -> dict[str, object]:
    return {
        "schema_version": "manim-quality.geometry-fact.v1",
        "engine_version": "geometry-inspector-v1",
        "code_hash": CODE_HASH,
        "snapshot_hash": SNAPSHOT_HASH,
        "relation": "perpendicular",
        "status": status,
        "truth": False if status == "known" else None,
        "observed": {"normalized_dot_product": 0.25} if status == "known" else {},
        "evidence": [source()],
        "assumptions": [],
        "reason_code": None if status == "known" else "dynamic_value",
    }


def test_fact_known_and_unknown_invariants_are_explicit() -> None:
    known = parse_geometry_fact(fact_payload())
    unknown = parse_geometry_fact(fact_payload(status="unknown"))

    assert isinstance(known, GeometryFact)
    assert known.truth is False
    assert unknown.truth is None
    assert unknown.reason_code == "dynamic_value"


@pytest.mark.parametrize(
    "change",
    [
        {"status": "known", "truth": None},
        {"status": "known", "truth": True, "reason_code": "timeout"},
        {"status": "unknown", "truth": False, "reason_code": "dynamic_value"},
        {"status": "unknown", "truth": None, "reason_code": None},
    ],
)
def test_fact_rejects_status_truth_mismatches(change: dict[str, object]) -> None:
    payload = fact_payload()
    payload.update(change)

    with pytest.raises(ValueError):
        parse_geometry_fact(payload)


def test_fact_rejects_unlisted_observations_and_assumptions() -> None:
    payload = fact_payload()
    payload["observed"] = {"diagnosis": "wrong relation"}
    with pytest.raises(ValueError):
        parse_geometry_fact(payload)

    payload = fact_payload()
    payload["assumptions"] = ["repair_hint: move point"]
    with pytest.raises(ValueError):
        parse_geometry_fact(payload)
