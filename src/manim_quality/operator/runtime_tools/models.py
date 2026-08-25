"""Internal immutable results for real revision checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RenderResult:
    ok: bool
    revision_dir: Path
    candidate_path: Path
    video_path: Path | None
    duration_seconds: float | None
    error: str | None
    cache_hit_count: int = 0
    new_partial_count: int = 0
    elapsed_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ProbeResult:
    ok: bool
    raw_path: Path
    payload: dict[str, object]
    error: str | None
