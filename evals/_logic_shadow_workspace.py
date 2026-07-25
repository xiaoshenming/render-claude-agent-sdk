"""Build a diagnosis-free workspace for one frozen shadow case."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from manim_quality.logic.eval_manifest import FrozenEvalCase

_SCENE_METADATA_FILES = ("case_manifest.json", "sample_meta.json")


def copy_scene_identity(case: FrozenEvalCase, root: Path, workspace: Path) -> None:
    for name in _SCENE_METADATA_FILES:
        artifact = case.artifacts.get(name)
        if artifact is None:
            continue
        try:
            payload = json.loads(
                artifact.resolve_verified(root).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        scene_name = payload.get("scene_name") if isinstance(payload, Mapping) else None
        if isinstance(scene_name, str) and scene_name.strip():
            content = json.dumps({"scene_name": scene_name.strip()}, ensure_ascii=False)
            (workspace / "case_manifest.json").write_text(content, encoding="utf-8")
            return
