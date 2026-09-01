"""Verified bridge to the frozen overlap issue classifier."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from .candidate_recovery import recover_candidates


class LayoutIssueDetector:
    def __init__(self, checker_path: Path) -> None:
        self._checker_path = checker_path.resolve(strict=True)
        self._module = _load_module(self._checker_path)

    def detect(
        self,
        raw_probe: dict[str, object],
        *,
        artifact_path: Path,
    ) -> dict[str, object]:
        probe = {"ok": True, **raw_probe}
        payload = self._module.payload_from_probe(probe)
        if not isinstance(payload, dict):
            raise TypeError("layout detector returned a malformed payload")
        payload = recover_candidates(probe, payload)
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_manim_quality_layout_probe_check",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load layout detector: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "payload_from_probe", None)):
        raise ImportError("layout detector has no payload_from_probe")
    return module
