from __future__ import annotations

import json
from pathlib import Path

from .models import AssuranceCase


def load_annotated_cases(
    forensic_dir: Path,
    gallery_dir: Path,
    logs_dir: Path,
) -> tuple[AssuranceCase, ...]:
    annotations = _object(forensic_dir / "human_annotations.json")
    explanations = _object(forensic_dir / "case_explanations_41.json").get(
        "cases", {}
    )
    gallery = _object(gallery_dir / "manifest.json").get("items", [])
    by_key = {
        row.get("external_key"): row
        for row in gallery
        if isinstance(row, dict) and isinstance(row.get("external_key"), str)
    }
    tag_map: dict[str, list[str]] = {}
    for tag, keys in annotations.items():
        if not isinstance(keys, list):
            continue
        for key in keys:
            if isinstance(key, str):
                tag_map.setdefault(key, []).append(tag)
    cases = []
    if not isinstance(explanations, dict):
        return ()
    for key, explanation in explanations.items():
        item = by_key.get(key, {})
        stage = _selected_stage(item.get("stages"))
        relative = stage.get("path") if isinstance(stage, dict) else None
        video = gallery_dir / str(relative or "missing.mp4")
        verdict = explanation.get("verdict") if isinstance(explanation, dict) else ""
        cases.append(
            AssuranceCase(
                key=key,
                question=str(item.get("question") or ""),
                human_tags=tuple(sorted(tag_map.get(key, ()))),
                expected_verdict=str(verdict or ""),
                video_path=video,
                log_dir=logs_dir / key,
            )
        )
    return tuple(cases)


def _selected_stage(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    for name in ("overlap", "logic", "before"):
        stage = value.get(name)
        if isinstance(stage, dict) and stage.get("path"):
            return stage
    return {}


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}
