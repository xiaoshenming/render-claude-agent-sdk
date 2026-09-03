"""Capture layout snapshots while the real Manim render is running."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .geometry_sidecar_runner import _load_delegate, _shape_records
from .semantic_rows import collect, dedupe, install_tagging
from .semantic_rows import overlaps as row_overlaps

PAYLOAD_ENV = "MANIM_COMBINED_BBOX_PATH"
SIDECAR_ENV = "MANIM_COMBINED_GEOMETRY_PATH"
SCENE_ENV = "MANIM_COMBINED_SCENE"


class _Capture:
    def __init__(self, delegate, payload_path: Path, sidecar_path: Path) -> None:
        self.delegate = delegate
        self.payload_path = payload_path
        self.sidecar_path = sidecar_path
        self.snapshots: list[dict[str, Any]] = []
        self.geometry: list[dict[str, Any]] = []
        self.warnings: list[dict[str, str]] = []
        self.last_frame_sample = -1.0

    def snapshot_frame(self, scene: Any) -> None:
        timestamp = _scene_time(scene)
        if timestamp <= 0 or timestamp - self.last_frame_sample < 0.5:
            return
        self.last_frame_sample = timestamp
        self.snapshot(scene, "during_play", persist=False)

    def snapshot(self, scene: Any, event: str, *, persist: bool = True) -> None:
        try:
            for mob in list(getattr(scene, "mobjects", []) or []):
                try:
                    mob.update(0)
                except Exception:
                    pass
            items = self.delegate._collect_objects(scene)
            if event == "during_play":
                visible = _visible_paths(scene)
                items = [row for row in items if row.get("path") in visible]
            semantic = collect(scene, self.delegate)
            from manim import config

            step = int(getattr(scene, "_combined_capture_step", 0))
            timestamp = _scene_time(scene)
            overlaps = self.delegate._find_overlaps(items)[:40]
            bounds = self.delegate._find_frame_bounds_violations(
                items,
                frame_width=float(config.frame_width),
                frame_height=float(config.frame_height),
            )[:40]
            self.snapshots.append({
                "scene": scene.__class__.__name__,
                "step": step,
                "event": event,
                "time_window": {
                    "start": timestamp,
                    "end": timestamp,
                    "recommended_timestamp": timestamp,
                },
                "estimated_duration": timestamp,
                "object_count": len(items),
                "objects": items,
                "overlaps": overlaps,
                "semantic_row_overlaps": row_overlaps(semantic),
                "bounds_violations": bounds,
            })
            self.geometry.append({"step": step, "shapes": _shape_records(items)})
            if persist:
                self._persist()
        except Exception as error:  # one bad object must not erase valid evidence
            self.warnings.append({
                "scene": scene.__class__.__name__,
                "error": f"{type(error).__name__}: {error}",
            })
            self._persist()

    def _persist(self) -> None:
        overlaps = [
            {"scene": row["scene"], "step": row["step"],
             "event": row["event"], "time_window": row["time_window"], **item}
            for row in self.snapshots for item in row["overlaps"]
        ]
        bounds = [
            {"scene": row["scene"], "step": row["step"],
             "event": row["event"], "time_window": row["time_window"], **item}
            for row in self.snapshots for item in row["bounds_violations"]
        ]
        semantic = [
            {"scene": row["scene"], "step": row["step"],
             "event": row["event"], "time_window": row["time_window"], **item}
            for row in self.snapshots for item in row["semantic_row_overlaps"]
        ]
        overlaps.sort(key=lambda item: item["ratio_of_smaller"], reverse=True)
        bounds.sort(
            key=lambda item: max(item["overflow_x"], item["overflow_y"]),
            reverse=True,
        )
        semantic.sort(key=lambda item: item["ratio_of_smaller"], reverse=True)
        payload = {
            "capture_mode": "combined_real_render",
            "scene": self.snapshots[-1]["scene"] if self.snapshots else None,
            "error_count": 0,
            "errors": [],
            "warning_count": len(self.warnings),
            "warnings": self.warnings,
            "snapshot_count": len(self.snapshots),
            "estimated_duration": max(
                (row["estimated_duration"] for row in self.snapshots), default=0.0),
            "top_overlaps": self.delegate._dedupe_overlaps(overlaps)[:80],
            "semantic_row_overlaps": dedupe(semantic)[:80],
            "top_bounds_violations": (
                self.delegate._dedupe_bounds_violations(bounds)[:80]),
        }
        _atomic_json(self.payload_path, payload)
        _atomic_json(self.sidecar_path, {
            "version": 1,
            "capture_mode": "combined_real_render",
            "captures": self.geometry,
        })


def install() -> bool:
    payload = os.environ.get(PAYLOAD_ENV, "").strip()
    delegate_path = os.environ.get("MANIM_LAYOUT_PROBE_DELEGATE", "").strip()
    if not payload or not delegate_path:
        return False
    from manim import Mobject, Scene

    capture = _Capture(
        _load_delegate(Path(delegate_path)),
        Path(payload),
        Path(os.environ.get(SIDECAR_ENV) or Path(payload).with_name(
            "combined_geometry_sidecar.json")),
    )
    target = os.environ.get(SCENE_ENV, "Solution").strip() or "Solution"
    original_play = Scene.play
    original_wait, original_render = Scene.wait, Scene.render
    install_tagging(Mobject)

    def selected(scene: Any) -> bool:
        return scene.__class__.__name__ == target

    def play(scene: Any, *args: Any, **kwargs: Any):
        result = original_play(scene, *args, **kwargs)
        if selected(scene):
            scene._combined_capture_step = int(
                getattr(scene, "_combined_capture_step", 0)) + 1
            capture.snapshot(scene, "after_play")
        return result

    def wait(scene: Any, *args: Any, **kwargs: Any):
        result = original_wait(scene, *args, **kwargs)
        if selected(scene):
            scene._combined_capture_step = int(
                getattr(scene, "_combined_capture_step", 0)) + 1
            capture.snapshot(scene, "after_wait")
        return result

    def render(scene: Any, *args: Any, **kwargs: Any):
        result = original_render(scene, *args, **kwargs)
        if selected(scene):
            capture.snapshot(scene, "end")
        return result

    Scene.play, Scene.wait, Scene.render = play, wait, render
    _install_frame_sampling(Scene, capture, selected)
    return True


def _install_frame_sampling(scene_type, capture, selected) -> None:
    original = scene_type.update_to_time

    def update_to_time(scene: Any, timestamp: float):
        result = original(scene, timestamp)
        if selected(scene):
            capture.snapshot_frame(scene)
        return result

    scene_type.update_to_time = update_to_time


def _visible_paths(scene: Any) -> set[str]:
    visible = set()

    def walk(mob: Any, path: str) -> bool:
        child_visible = False
        for index, child in enumerate(getattr(mob, "submobjects", ()) or ()):
            child_visible = walk(child, f"{path}.{index}") or child_visible
        current = _visible_opacity(mob) > 0.02
        if current or child_visible:
            visible.add(path)
        return current or child_visible

    for index, mob in enumerate(getattr(scene, "mobjects", ()) or ()):
        walk(mob, f"mobjects.{index}")
    return visible


def _visible_opacity(mob: Any) -> float:
    values = []
    for name in ("get_opacity", "get_fill_opacity", "get_stroke_opacity"):
        method = getattr(mob, name, None)
        if not callable(method):
            continue
        try:
            value = method()
            if hasattr(value, "flatten"):
                value = value.flatten().tolist()
            if isinstance(value, (list, tuple)):
                values.extend(float(item) for item in value)
            else:
                values.append(float(value))
        except (TypeError, ValueError):
            continue
    return max(values, default=0.0)


def _scene_time(scene: Any) -> float:
    try:
        return round(max(0.0, float(scene.renderer.time)), 4)
    except Exception:
        return 0.0


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
