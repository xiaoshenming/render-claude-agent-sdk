"""Execute the frozen V3 existing-code Harness and return its selected code."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class V3RunResult:
    selected_code: str
    final_video_path: Path | None
    status: str
    fail_open_used: bool
    result_path: Path | None
    evidence: dict[str, Any]


def _layout_token_budget() -> int:
    raw = os.environ.get("MANIM_QUALITY_LAYOUT_TOKEN_BUDGET", "180000")
    try:
        value = int(raw)
    except ValueError:
        value = 180_000
    return min(300_000, max(60_000, value))


def run_v3_existing_code(
    *,
    job_id: str,
    candidate_code: str,
    problem_text: str,
    expected_solution: str,
    output_dir: Path,
) -> V3RunResult:
    root = Path(
        os.environ.get(
            "MANIM_QUALITY_V3_ROOT",
            str(Path(__file__).resolve().parents[2] / "manim_quality_platform/v3"),
        )
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = output_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    code_path = inputs / "candidate.py"
    problem_path = inputs / "problem.txt"
    expected_path = inputs / "expected_solution.txt"
    code_path.write_text(candidate_code, encoding="utf-8")
    problem_path.write_text(problem_text, encoding="utf-8")
    expected_path.write_text(expected_solution, encoding="utf-8")
    run_dir = output_dir / "run"
    command = [
        sys.executable,
        str(root / "scripts/run_existing_code_e2e.py"),
        "--code", str(code_path),
        "--problem", str(problem_path),
        "--expected-solution", str(expected_path),
        "--manim-python",
        os.environ.get(
            "MANIM_QUALITY_MANIM_PYTHON",
            str(Path(__file__).with_name("manim_python_adapter.py")),
        ),
        "--output", str(run_dir),
        "--job-id", job_id,
        "--layout-token-budget", str(_layout_token_budget()),
        "--allow-vendor-clean-fallback",
    ]
    env = os.environ.copy()
    env.update(_provider_env())
    render_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (render_root, env.get("PYTHONPATH", "")) if value
    )
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        result_path = run_dir / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        final_path = run_dir / "candidate_final.py"
        status = str(payload.get("status") or "unknown")
        if completed.returncode == 0 and status in {"deliver", "deliver_with_warning"}:
            selected = final_path.read_text(encoding="utf-8")
            video_path = run_dir / "video_final.mp4"
            if not video_path.is_file():
                raise FileNotFoundError(f"V3 final video missing: {video_path}")
            return V3RunResult(
                selected, video_path, status, False, result_path, payload
            )
        error = f"v3_exit={completed.returncode}; status={status}"
    except Exception as exc:  # noqa: BLE001 - playable FAST_PRE code survives.
        payload = {}
        result_path = None
        error = f"{type(exc).__name__}: {exc}"
    return V3RunResult(
        candidate_code,
        None,
        "fail_open",
        True,
        result_path,
        {**payload, "bridge_error": error[:1000]},
    )


def _provider_env() -> dict[str, str]:
    key = str(settings.MANIM_QUALITY_ANTHROPIC_API_KEY or "").strip()
    base_url = str(settings.MANIM_QUALITY_ANTHROPIC_BASE_URL or "").strip()
    model = str(settings.MANIM_QUALITY_MODEL or "").strip()
    return {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": key,
        "MANIM_QUALITY_API_KEY": key,
        "QUALITY_MODEL": model,
    }
