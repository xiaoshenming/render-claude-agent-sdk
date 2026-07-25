from __future__ import annotations

import ast
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .process_env import sanitized_subprocess_env


@dataclass(frozen=True, slots=True)
class RenderResult:
    succeeded: bool
    scene_name: str
    video_path: Path | None
    elapsed_ms: int
    returncode: int
    command: tuple[str, ...]
    error: str | None = None


class LocalManimRenderer:
    def __init__(
        self,
        *,
        python: str,
        quality: str = "l",
        timeout_seconds: int = 420,
        runner: Callable[..., object] = subprocess.run,
    ) -> None:
        self._python = python
        self._quality = quality
        self._timeout = timeout_seconds
        self._runner = runner

    def render(self, source: Path, output_dir: Path) -> RenderResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        scene = scene_name(source.read_text(encoding="utf-8"))
        command = (
            self._python,
            "-m",
            "manim",
            f"-q{self._quality}",
            "--disable_caching",
            "--media_dir",
            str(output_dir.resolve()),
            "-o",
            "result",
            str(source.resolve()),
            scene,
        )
        started = time.perf_counter()
        try:
            completed = self._runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
                env=sanitized_subprocess_env(),
            )
            elapsed = round((time.perf_counter() - started) * 1_000)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            (output_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (output_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            video = _find_video(output_dir) if completed.returncode == 0 else None
            result = RenderResult(
                succeeded=video is not None,
                scene_name=scene,
                video_path=video,
                elapsed_ms=elapsed,
                returncode=completed.returncode,
                command=command,
                error=None if video else _tail(stderr or stdout),
            )
        except subprocess.TimeoutExpired as error:
            result = RenderResult(
                False,
                scene,
                None,
                round((time.perf_counter() - started) * 1_000),
                -1,
                command,
                f"render_timeout:{error.timeout}",
            )
        _write_result(output_dir / "render.json", result)
        return result


def scene_name(source: str) -> str:
    tree = ast.parse(source)
    candidates = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(item, ast.FunctionDef) and item.name == "construct"
            for item in node.body
        )
    ]
    if "Solution" in candidates:
        return "Solution"
    if not candidates:
        raise ValueError("candidate contains no renderable Scene")
    return candidates[-1]


def _find_video(root: Path) -> Path | None:
    matches = sorted(root.rglob("result.mp4"), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


def _tail(value: str, limit: int = 4_000) -> str:
    return value[-limit:].strip() or "render produced no video"


def _write_result(path: Path, result: RenderResult) -> None:
    payload = asdict(result)
    payload["video_path"] = str(result.video_path) if result.video_path else None
    payload["command"] = list(result.command)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
