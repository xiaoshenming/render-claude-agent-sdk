"""Multi-snapshot BBox probe bound to the rendered revision."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .models import ProbeResult
from .process import read_last_json_line, run_to_artifacts


class BBoxProbe:
    def __init__(
        self,
        *,
        source_workspace: Path,
        runner_path: Path,
        python_executable: Path,
        environment: dict[str, str] | None = None,
        scene_name: str = "Solution",
        timeout_seconds: int = 1_200,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._workspace = source_workspace.resolve(strict=True)
        self._runner = runner_path.resolve(strict=True)
        self._python = python_executable.resolve(strict=True)
        self._environment = dict(environment or {})
        self._scene = scene_name
        self._timeout = timeout_seconds
        self._width = width
        self._height = height

    def inspect(self, revision_dir: Path, candidate: Path) -> ProbeResult:
        raw_path = revision_dir / "bbox_probe.json"
        environment = {
            **self._environment,
            "MANIM_LAYOUT_PROBE_MEDIA_DIR": str(revision_dir / "media"),
        }
        argv = [
            str(self._python),
            str(self._runner),
            str(candidate),
            "--scene",
            self._scene,
            "--width",
            str(self._width),
            "--height",
            str(self._height),
        ]
        try:
            result = run_to_artifacts(
                argv,
                cwd=self._workspace,
                timeout_seconds=self._timeout,
                stdout_path=revision_dir / "bbox_probe.stdout.log",
                stderr_path=revision_dir / "bbox_probe.stderr.log",
                env_overrides=environment,
            )
            payload = read_last_json_line(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            return ProbeResult(False, raw_path, {}, f"bbox_probe:{error}")
        raw_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if result.returncode != 0 or int(payload.get("error_count") or 0) > 0:
            return ProbeResult(False, raw_path, payload, "bbox_probe_not_ok")
        return ProbeResult(True, raw_path, payload, None)
