"""Persist verified video and combined layout evidence by source SHA."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from .models import RenderResult


class VerificationRenderer:
    def __init__(self, renderer, cache_root: Path | None) -> None:
        self.renderer = renderer
        self.cache_root = (
            Path(cache_root) / "verification_receipts" if cache_root else None)

    def render(
        self, revision_dir: Path, candidate: Path, code_hash: str,
    ) -> RenderResult:
        restored = self._restore(revision_dir, candidate, code_hash)
        if restored is not None:
            return restored
        result = self.renderer.render(revision_dir, candidate)
        if result.ok:
            self._store(result, code_hash)
        return result

    def _restore(
        self, revision_dir: Path, candidate: Path, code_hash: str,
    ) -> RenderResult | None:
        root = self._entry(code_hash)
        if root is None:
            return None
        receipt = root / "receipt.json"
        files = {
            "video": root / "verified_video.mp4",
            "bbox": root / "combined_bbox_probe.json",
            "geometry": root / "combined_geometry_sidecar.json",
        }
        if not receipt.is_file() or not all(path.is_file() for path in files.values()):
            return None
        try:
            metadata = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("code_hash") != code_hash:
            return None
        revision_dir.mkdir(parents=True, exist_ok=True)
        targets = {
            "video": revision_dir / "verified_video.mp4",
            "bbox": revision_dir / "combined_bbox_probe.json",
            "geometry": revision_dir / "combined_geometry_sidecar.json",
        }
        for name, source in files.items():
            shutil.copy2(source, targets[name])
        return RenderResult(
            True, revision_dir, candidate, targets["video"],
            float(metadata["duration_seconds"]), None,
            cache_hit_count=int(metadata.get("cache_hit_count") or 0) + 1,
            new_partial_count=0,
            elapsed_ms=0,
        )

    def _store(self, result: RenderResult, code_hash: str) -> None:
        root = self._entry(code_hash)
        if root is None or result.video_path is None:
            return
        sources = {
            "verified_video.mp4": result.video_path,
            "combined_bbox_probe.json": (
                result.revision_dir / "combined_bbox_probe.json"),
            "combined_geometry_sidecar.json": (
                result.revision_dir / "combined_geometry_sidecar.json"),
        }
        if not all(path.is_file() for path in sources.values()):
            return
        root.mkdir(parents=True, exist_ok=True)
        for name, source in sources.items():
            shutil.copy2(source, root / name)
        _atomic_json(root / "receipt.json", {
            "schema_version": "manim-quality.verification-receipt.v1",
            "code_hash": code_hash,
            "duration_seconds": result.duration_seconds,
            "cache_hit_count": result.cache_hit_count,
        })

    def _entry(self, code_hash: str) -> Path | None:
        if self.cache_root is None:
            return None
        digest = code_hash.removeprefix("sha256:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            return None
        return self.cache_root / digest


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
