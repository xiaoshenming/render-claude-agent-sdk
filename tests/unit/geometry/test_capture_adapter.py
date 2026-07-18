from dataclasses import dataclass

from manim_quality.geometry.capture_adapter import (
    RuntimeObservation,
    capture_runtime_snapshot,
)

CODE_HASH = "sha256:" + "c" * 64


def source(line: int) -> dict[str, object]:
    return {
        "scene_id": "Solution",
        "line_start": line,
        "line_end": line,
        "excerpt": f"runtime object at line {line}",
    }


@dataclass
class FakePoint:
    center: tuple[float, float, float]

    def get_center(self):
        return self.center


@dataclass
class FakeLine:
    start: tuple[float, float, float]
    end: tuple[float, float, float]

    def get_start(self):
        return self.start

    def get_end(self):
        return self.end


@dataclass
class FakeCircle:
    center: tuple[float, float, float]
    radius: float

    def get_center(self):
        return self.center


@dataclass
class FakePolygon:
    vertices: tuple[tuple[float, float, float], ...]

    def get_vertices(self):
        return self.vertices


def test_capture_adapter_reads_supported_objects_without_manim_dependency() -> None:
    observations = (
        RuntimeObservation("A", "point", FakePoint((1, 2, 0)), source(10)),
        RuntimeObservation(
            "line_ab", "line", FakeLine((1, 2, 0), (4, 2, 0)), source(11)
        ),
        RuntimeObservation("circle", "circle", FakeCircle((0, 0, 0), 2), source(12)),
        RuntimeObservation(
            "triangle",
            "polygon",
            FakePolygon(((0, 0, 0), (1, 0, 0), (0, 1, 0))),
            source(13),
        ),
    )

    snapshot = capture_runtime_snapshot(
        code_hash=CODE_HASH,
        scene_id="Solution",
        checkpoint_id="play-7",
        observations=observations,
    )

    assert snapshot.provenance == "runtime_checkpoint"
    assert snapshot.object("A").state["position"] == (1, 2, 0)
    assert snapshot.object("line_ab").state["end"] == (4, 2, 0)
    assert snapshot.object("circle").state["radius"] == 2
    assert len(snapshot.object("triangle").state["vertices"]) == 3


def test_missing_runtime_accessor_becomes_unknown() -> None:
    observation = RuntimeObservation("bad", "line", object(), source(20))

    snapshot = capture_runtime_snapshot(
        code_hash=CODE_HASH,
        scene_id="Solution",
        checkpoint_id="final-visible",
        observations=(observation,),
        final=True,
    )

    item = snapshot.object("bad")
    assert snapshot.provenance == "runtime_final"
    assert item.status.value == "unknown"
    assert item.reason_code == "unsupported_object"


def test_duplicate_runtime_identity_is_rejected_by_snapshot_contract() -> None:
    observation = RuntimeObservation("A", "point", FakePoint((0, 0, 0)), source(30))

    try:
        capture_runtime_snapshot(
            code_hash=CODE_HASH,
            scene_id="Solution",
            checkpoint_id="play-1",
            observations=(observation, observation),
        )
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate runtime identity must be rejected")


def test_source_scene_must_match_runtime_scene() -> None:
    bad_source = {**source(40), "scene_id": "Other"}
    observation = RuntimeObservation("A", "point", FakePoint((0, 0, 0)), bad_source)

    try:
        capture_runtime_snapshot(
            code_hash=CODE_HASH,
            scene_id="Solution",
            checkpoint_id="play-1",
            observations=(observation,),
        )
    except ValueError as error:
        assert "scene" in str(error)
    else:
        raise AssertionError("cross-scene source binding must be rejected")
