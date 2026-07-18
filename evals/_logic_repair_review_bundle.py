"""Deterministic identity for the Reviewer summary and per-case reports."""

from __future__ import annotations

import json
from pathlib import Path

from manim_quality.revisions.fingerprint import sha256_bytes, sha256_text


def review_bundle_hash(root: Path) -> str:
    base = Path(root).resolve(strict=True)
    paths = [base / "shadow_report.json"]
    paths.extend(sorted((base / "cases").glob("*/review_report.json")))
    entries: list[dict[str, str]] = []
    for raw in paths:
        path = raw.resolve(strict=True)
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError("Reviewer evidence path escapes bundle root")
        entries.append(
            {
                "path": path.relative_to(base).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)
