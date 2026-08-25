"""Real Manim render plus ffprobe stream verification."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from .models import RenderResult
from .process import run_to_artifacts


class ManimRenderer:
    def __init__(
        self,
        *,
        source_workspace: Path,
        python_executable: Path,
        environment: dict[str, str] | None = None,
        scene_name: str = "Solution",
        timeout_seconds: int = 1_200,
        quality: str = "l",
        cache_dir: Path | None = None,
    ) -> None:
        self._workspace = source_workspace.resolve(strict=True)
        self._python = python_executable.resolve(strict=True)
        self._environment = dict(environment or {})
        self._scene = scene_name
        self._timeout = timeout_seconds
        self._quality = quality
        # A shared cache_dir enables Manim's content-hashed partial-movie
        # cache across revisions of one problem: unchanged animations are
        # reused, only edited segments re-render. Callers keep this OFF for
        # the acceptance gate so delivered videos are always cold renders.
        self._cache_dir = cache_dir

    def render(self, revision_dir: Path, candidate: Path) -> RenderResult:
        media = self._cache_dir or (revision_dir / "media")
        partials_before = _partial_movies(media)
        started = time.perf_counter()
        argv = [
            str(self._python),
            "-m",
            "manim",
            str(candidate),
            self._scene,
            f"-q{self._quality}",
            "--media_dir",
            str(media),
        ]
        if self._cache_dir is None:
            argv.append("--disable_caching")
        try:
            result = run_to_artifacts(
                argv,
                cwd=self._workspace,
                timeout_seconds=self._timeout,
                stdout_path=revision_dir / "render.stdout.log",
                stderr_path=revision_dir / "render.stderr.log",
                env_overrides=self._environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return _failed(
                revision_dir, candidate, f"render_process:{error}", started)
        if result.returncode != 0:
            return _failed(
                revision_dir,
                candidate,
                f"manim_exit_code:{result.returncode}",
                started,
            )
        video = _newest_video(media)
        if video is None:
            return _failed(
                revision_dir, candidate, "render_video_missing", started)
        try:
            duration = _probe_video(video, revision_dir, self._timeout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            return _failed(revision_dir, candidate, f"ffprobe:{error}", started)
        partials_after = _partial_movies(media)
        return RenderResult(
            True,
            revision_dir,
            candidate,
            video,
            duration,
            None,
            cache_hit_count=result.stdout.count("Using cached data"),
            new_partial_count=len(partials_after - partials_before),
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )


def _newest_video(media: Path) -> Path | None:
    videos = [
        path
        for path in media.rglob("*.mp4")
        if path.is_file() and "partial_movie_files" not in path.parts
    ]
    return max(videos, key=lambda path: path.stat().st_mtime_ns) if videos else None


def _partial_movies(media: Path) -> set[Path]:
    if not media.is_dir():
        return set()
    return {
        path.relative_to(media)
        for path in media.rglob("*.mp4")
        if path.is_file() and "partial_movie_files" in path.parts
    }


def _probe_video(video: Path, revision_dir: Path, timeout: int) -> float:
    argv = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video),
    ]
    result = run_to_artifacts(
        argv,
        cwd=revision_dir,
        timeout_seconds=min(timeout, 60),
        stdout_path=revision_dir / "ffprobe.json",
        stderr_path=revision_dir / "ffprobe.stderr.log",
    )
    if result.returncode != 0:
        raise ValueError(f"exit_code:{result.returncode}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("ffprobe returned a non-object payload")
    duration = float(dict(payload.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("non_positive_duration")
    return duration


def _failed(
    revision_dir: Path,
    candidate: Path,
    error: str,
    started: float | None = None,
) -> RenderResult:
    return RenderResult(
        False,
        revision_dir,
        candidate,
        None,
        None,
        error,
        elapsed_ms=(
            round((time.perf_counter() - started) * 1000)
            if started is not None else None
        ),
    )
