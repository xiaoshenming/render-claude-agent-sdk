"""Capture layout snapshots while the real Manim render is running."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .geometry_sidecar_runner import _load_delegate, _shape_records
from .semantic_rows import (
    collect_semantic_rows,
    dedupe_semantic,
    install_semantic_tagging,
    semantic_row_overlaps,
)

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
        self.errors: list[dict[str, str]] = []

    def snapshot(self, scene: Any, event: str) -> None:
        try:
            for mob in list(getattr(scene, "mobjects", []) or []):
                try:
                    mob.update(0)
                except Exception:
                    pass
            items = self.delegate._collect_objects(scene)
            semantic_rows = collect_semantic_rows(scene, self.delegate)
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
                "semantic_row_overlaps": semantic_row_overlaps(semantic_rows),
                "bounds_violations": bounds,
            })
            self.geometry.append({"step": step, "shapes": _shape_records(items)})
            self._persist()
        except Exception as error:  # capture must never break video delivery
            self.errors.append({
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
            "error_count": len(self.errors),
            "errors": self.errors,
            "snapshot_count": len(self.snapshots),
            "estimated_duration": max(
                (row["estimated_duration"] for row in self.snapshots), default=0.0),
            "top_overlaps": self.delegate._dedupe_overlaps(overlaps)[:80],
            "semantic_row_overlaps": dedupe_semantic(semantic)[:80],
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
    original_play, original_wait, original_render = Scene.play, Scene.wait, Scene.render
    install_semantic_tagging(Mobject)

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
    return True


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
