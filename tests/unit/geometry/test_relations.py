import pytest

from manim_quality.geometry.relations import inspect_relation
from manim_quality.geometry.schemas import parse_geometry_snapshot

CODE_HASH = "sha256:" + "a" * 64


def source(line: int) -> dict[str, object]:
    return {
        "scene_id": "Solution",
        "line_start": line,
        "line_end": line,
        "excerpt": f"object at line {line}",
    }


def obj(
    object_id: str,
    kind: str,
    state: dict[str, object],
    line: int,
    *,
    status: str = "known",
) -> dict[str, object]:
    return {
        "object_id": object_id,
        "kind": kind,
        "status": status,
        "reason_code": None if status == "known" else "dynamic_value",
        "state": state if status == "known" else {},
        "source": source(line),
    }


def snapshot(*objects: dict[str, object]):
    return parse_geometry_snapshot(
        {
            "schema_version": "manim-quality.geometry-snapshot.v1",
            "code_hash": CODE_HASH,
            "scene_id": "Solution",
            "checkpoint_id": "final-visible",
            "provenance": "runtime_checkpoint",
            "objects": list(objects),
        }
    )


def point(name: str, value: list[int | float], line: int) -> dict[str, object]:
    return obj(name, "point", {"position": value}, line)


def line(
    name: str,
    start: list[int | float],
    end: list[int | float],
    source_line: int,
    *,
    start_ref: str | None = None,
    end_ref: str | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {"start": start, "end": end}
    if start_ref is not None:
        state["start_ref"] = start_ref
    if end_ref is not None:
        state["end_ref"] = end_ref
    return obj(name, "line", state, source_line)


@pytest.mark.parametrize(
    ("relation", "operands", "expected"),
    [
        ("parallel", ("horizontal", "horizontal_2"), True),
        ("parallel", ("horizontal", "vertical"), False),
        ("perpendicular", ("horizontal", "vertical"), True),
        ("perpendicular", ("horizontal", "diagonal"), False),
        ("equal_length", ("horizontal", "vertical"), True),
        ("equal_length", ("horizontal", "diagonal"), False),
    ],
)
def test_line_relations_return_source_bound_facts(
    relation: str, operands: tuple[str, ...], expected: bool
) -> None:
    geometry = snapshot(
        line("horizontal", [0, 0], [2, 0], 10),
        line("horizontal_2", [3, 1], [5, 1], 11),
        line("vertical", [1, -1], [1, 1], 12),
        line("diagonal", [0, 0], [1, 1], 13),
    )

    fact = inspect_relation(geometry, relation, operands)

    assert fact.status.value == "known"
    assert fact.truth is expected
    assert fact.code_hash == CODE_HASH
    assert fact.snapshot_hash == geometry.snapshot_hash
    assert {item.line_start for item in fact.evidence} == {
        geometry.object(name).source.line_start for name in operands
    }


def test_point_and_three_point_relations() -> None:
    geometry = snapshot(
        point("A", [0, 0], 20),
        point("B", [2, 0], 21),
        point("M", [1, 0], 22),
        point("P", [4, 0], 23),
        point("Q", [1, 1], 24),
        line("AB", [0, 0], [2, 0], 25),
        obj("circle", "circle", {"center": [0, 0], "radius": 1}, 26),
    )

    assert inspect_relation(geometry, "collinear", ("A", "B", "P")).truth
    assert inspect_relation(geometry, "midpoint", ("M", "A", "B")).truth
    assert inspect_relation(geometry, "point_on_line", ("P", "AB")).truth
    assert inspect_relation(geometry, "point_on_circle", ("Q", "circle")).truth is False
    assert inspect_relation(geometry, "point_on_circle", ("M", "circle")).truth


def test_line_endpoint_binding_allows_reverse_orientation() -> None:
    geometry = snapshot(
        point("A", [0, 0], 30),
        point("B", [2, 0], 31),
        line("AB", [2, 0], [0, 0], 32, start_ref="B", end_ref="A"),
    )

    fact = inspect_relation(geometry, "line_endpoints", ("AB", "A", "B"))

    assert fact.truth is True


@pytest.mark.parametrize(
    ("objects", "relation", "operands", "reason"),
    [
        (
            (line("zero", [0, 0], [0, 0], 40), line("valid", [0, 0], [1, 0], 41)),
            "parallel",
            ("zero", "valid"),
            "ambiguous_space",
        ),
        (
            (
                obj("dynamic", "point", {}, 42, status="unknown"),
                line("valid", [0, 0], [1, 0], 43),
            ),
            "point_on_line",
            ("dynamic", "valid"),
            "dynamic_value",
        ),
        (
            (point("A", [0, 0], 44),),
            "parallel",
            ("A", "missing"),
            "missing_entity",
        ),
    ],
)
def test_unsupported_or_ambiguous_relations_return_unknown(
    objects, relation: str, operands: tuple[str, ...], reason: str
) -> None:
    fact = inspect_relation(snapshot(*objects), relation, operands)

    assert fact.status.value == "unknown"
    assert fact.truth is None
    assert fact.reason_code == reason


def test_near_tolerance_boundary_returns_unknown_not_a_guess() -> None:
    geometry = snapshot(
        line("base", [0, 0], [1, 0], 50),
        line("almost", [0, 0], [1, 0.000005], 51),
    )

    fact = inspect_relation(geometry, "parallel", ("base", "almost"), tolerance=1e-6)

    assert fact.status.value == "unknown"
    assert fact.reason_code == "ambiguous_space"


def test_relation_is_translation_invariant() -> None:
    original = snapshot(
        line("a", [0, 0], [2, 0], 60),
        line("b", [1, -1], [1, 1], 61),
    )
    translated = snapshot(
        line("a", [10, -7], [12, -7], 60),
        line("b", [11, -8], [11, -6], 61),
    )

    assert inspect_relation(original, "perpendicular", ("a", "b")).truth
    assert inspect_relation(translated, "perpendicular", ("a", "b")).truth
