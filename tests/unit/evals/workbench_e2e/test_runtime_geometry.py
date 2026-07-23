import json

from evals.workbench_e2e.runtime_geometry import (
    _snapshot,
    geometry_snapshot_for_review,
)
from manim_quality.revisions.fingerprint import code_hash


CODE = """from manim import *
class Solution(Scene):
    def construct(self):
        A = Dot([0, 0, 0])
        B = Dot([1, 0, 0])
        edge = Line(A.get_center(), B.get_center())
        self.add(A, B, edge)
"""


def test_runtime_snapshot_uses_final_probe_positions():
    raw = [
        {
            "class": "Dot",
            "bbox": {
                "center_x": 2.0,
                "center_y": 3.0,
                "center_z": 0.0,
                "width": 0.1,
                "height": 0.1,
            },
        },
        {
            "class": "Line",
            "bbox": {},
            "geometry": {"points": [[2.0, 3.0], [4.0, 3.0]]},
        },
        {
            "class": "Dot",
            "bbox": {
                "center_x": 4.0,
                "center_y": 3.0,
                "center_z": 0.0,
                "width": 0.1,
                "height": 0.1,
            },
        },
    ]

    snapshot = _snapshot(CODE, "Solution", raw)

    assert snapshot.provenance == "runtime_final"
    assert snapshot.checkpoint_id == "runtime-final"
    assert snapshot.objects[0].state["position"] == (2.0, 3.0, 0.0)
    line = next(item for item in snapshot.objects if item.kind == "line")
    assert line.state["start"] == (2.0, 3.0, 0)


def test_runtime_snapshot_reuses_frozen_evidence(tmp_path):
    output = tmp_path / "runtime"
    output.mkdir()
    cached = {
        "schema_version": "manim-quality.geometry-snapshot.v1",
        "code_hash": code_hash("class Demo: pass"),
        "scene_id": "Demo",
        "checkpoint_id": "runtime-final",
        "provenance": "runtime_final",
        "objects": [],
    }
    (output / "runtime_geometry_snapshot.json").write_text(
        json.dumps(cached), encoding="utf-8"
    )

    snapshot = geometry_snapshot_for_review(
        code="class Demo: pass",
        candidate=tmp_path / "missing.py",
        runtime_python="/missing/python",
        probe_source=tmp_path / "missing-probe.py",
        output_dir=output,
    )

    assert snapshot.checkpoint_id == "runtime-final"
    assert snapshot.provenance == "runtime_final"
