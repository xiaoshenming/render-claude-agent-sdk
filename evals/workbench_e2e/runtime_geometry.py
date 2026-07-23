"""Capture a bounded final-state geometry snapshot through the Manim probe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from manim_quality.geometry.schemas import GeometrySnapshot, parse_geometry_snapshot
from manim_quality.geometry.static_index import build_static_geometry_snapshot
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.revisions.fingerprint import code_hash

from .layout_probe import _probe_source, parse_probe_stdout
from .process_env import sanitized_subprocess_env
from .rendering import scene_name


def geometry_snapshot_for_review(
    *,
    code: str,
    candidate: Path,
    runtime_python: str | None,
    probe_source: Path | None,
    output_dir: Path,
) -> GeometrySnapshot:
    cached = output_dir / "runtime_geometry_snapshot.json"
    if cached.is_file():
        try:
            snapshot = parse_geometry_snapshot(
                json.loads(cached.read_text(encoding="utf-8"))
            )
            if snapshot.code_hash == code_hash(code):
                return snapshot
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass
    if runtime_python and probe_source:
        try:
            return capture_final_geometry(
                code_path=candidate,
                python=runtime_python,
                probe_source=probe_source,
                output_dir=output_dir,
            )
        except Exception as error:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "error.json").write_text(
                json.dumps(
                    {
                        "status": "fallback_static",
                        "error": f"{type(error).__name__}: {error}",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
    return build_static_geometry_snapshot(code, scene_id=scene_name(code))


def capture_final_geometry(
    *,
    code_path: Path,
    python: str,
    probe_source: Path,
    output_dir: Path,
    timeout_seconds: int = 180,
) -> GeometrySnapshot:
    output_dir.mkdir(parents=True, exist_ok=True)
    code = code_path.read_text(encoding="utf-8")
    scene = scene_name(code)
    runner = output_dir / "runtime_geometry_probe.py"
    runner.write_text(
        _probe_source(probe_source, output_dir / "media"), encoding="utf-8"
    )
    completed = subprocess.run(
        [python, str(runner), str(code_path.resolve()), "--scene", scene],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        env=sanitized_subprocess_env(),
    )
    (output_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    probe = parse_probe_stdout(completed.stdout)
    if completed.returncode or probe.get("error_count"):
        raise RuntimeError(f"runtime_geometry_probe_failed:{completed.returncode}")
    snapshot = _snapshot(code, scene, probe.get("runtime_final_objects"))
    (output_dir / "runtime_geometry_snapshot.json").write_text(
        json.dumps(_snapshot_wire(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot


def _snapshot(code: str, scene: str, raw: object) -> GeometrySnapshot:
    objects = raw if isinstance(raw, list) else []
    static = build_static_geometry_snapshot(code, scene_id=scene)
    sources = _source_queues(static)
    captured = []
    runtime_by_kind = _runtime_states(objects)
    for kind, states in runtime_by_kind.items():
        # Source identity is only safe when runtime/static cardinality agrees.
        if len(states) != len(sources[kind]):
            continue
        for state, source_item in zip(states, sources[kind], strict=True):
            captured.append(_bound_runtime_object(kind, state, source_item))
    return parse_geometry_snapshot(
        {
            "schema_version": "manim-quality.geometry-snapshot.v1",
            "code_hash": code_hash(code),
            "scene_id": scene,
            "checkpoint_id": "runtime-final",
            "provenance": "runtime_final",
            "objects": captured[:160],
        }
    )


def _source_queues(snapshot: GeometrySnapshot) -> dict[str, list[object]]:
    queues = {kind: [] for kind in ("point", "line", "circle", "polygon")}
    for item in snapshot.objects:
        queues[item.kind].append(item)
    return queues


def _runtime_states(objects: list[object]) -> dict[str, list[dict]]:
    grouped = {kind: [] for kind in ("point", "line", "circle", "polygon")}
    for item in objects:
        if not isinstance(item, dict):
            continue
        kind, state = _state(item)
        if kind is not None:
            grouped[kind].append(state)
    return grouped


def _bound_runtime_object(kind: str, state: dict, source_item):
    source = source_item.source
    return {
        "object_id": source_item.object_id,
        "kind": kind,
        "status": "known",
        "reason_code": None,
        "state": state,
        "source": {
            "scene_id": source.scene_id,
            "line_start": source.line_start,
            "line_end": source.line_end,
            "excerpt": source.excerpt,
        },
    }


def _state(item: dict):
    name = str(item.get("class") or "")
    box = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
    geometry = item.get("geometry") if isinstance(item.get("geometry"), dict) else {}
    points = geometry.get("points") if isinstance(geometry.get("points"), list) else []
    if name in {"Dot", "SmallDot", "LabeledDot"} and box:
        return "point", {
            "position": [box["center_x"], box["center_y"], box.get("center_z", 0)]
        }
    if name in {"Line", "DashedLine", "Arrow", "DoubleArrow"} and len(points) >= 2:
        return "line", {"start": [*points[0], 0], "end": [*points[-1], 0]}
    if name == "Circle" and box:
        return "circle", {
            "center": [box["center_x"], box["center_y"], box.get("center_z", 0)],
            "radius": min(box["width"], box["height"]) / 2,
        }
    if name == "Polygon" and len(points) >= 3:
        return "polygon", {"vertices": [[*point, 0] for point in points]}
    return None, None


def _snapshot_wire(snapshot: GeometrySnapshot) -> dict[str, object]:
    return thaw_json_object(snapshot._wire)
