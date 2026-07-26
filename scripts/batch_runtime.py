"""Batch preflight and comparable runtime manifest."""

from __future__ import annotations

import ast
import json
import os
import platform
import subprocess
from pathlib import Path


def preflight(args, candidates: list[Path]) -> dict[str, object]:
    issues: list[str] = []
    for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        if os.environ.get(name, "").strip():
            break
    else:
        issues.append("provider authentication missing")
    for path, label in (
        (args.manim_python, "manim python"),
        (args.runtime_python_path, "runtime python path"),
    ):
        if not Path(path).exists():
            issues.append(f"{label} missing: {path}")
    for candidate in candidates:
        try:
            source = candidate.read_text(encoding="utf-8")
            ast.parse(source)
            compile(source, str(candidate), "exec")
        except Exception as error:
            issues.append(f"candidate invalid: {candidate}: {error}")
    docker = _command(["docker", "info", "--format", "{{.ServerVersion}}"])
    if docker["returncode"] != 0:
        issues.append("docker daemon unavailable")
    image = os.environ.get("MANIM_DOCKER_IMAGE", "docker-manim-worker-1:latest")
    image_id = _command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    if image_id["returncode"] != 0:
        issues.append(f"docker image unavailable: {image}")
    for command in ("ffmpeg", "ffprobe"):
        check = _command([command, "-version"])
        if check["returncode"] != 0:
            issues.append(f"{command} unavailable")
    manifest = {
        "status": "ok" if not issues else "failed",
        "issues": issues,
        "agent_commit": _text(["git", "rev-parse", "HEAD"], cwd=args.repo),
        "model": args.model,
        "effort": "low",
        "sdk_version": _package_version("claude-agent-sdk"),
        "docker_image": image,
        "docker_image_id": image_id["stdout"],
        "python_version": platform.python_version(),
        "manim_version": _docker_version(args.manim_python, "manim"),
        "ffmpeg_version": _first_line(["ffmpeg", "-version"]),
        "ffprobe_version": _first_line(["ffprobe", "-version"]),
        "detector_version": _detector_hash(args.repo),
        "render_quality": "480p15",
        "fps": 15,
        "tts_mode": "silent",
        "runtime_python_path": str(args.runtime_python_path),
        "agent_concurrency": args.agent_concurrency,
        "render_concurrency": args.render_concurrency,
        "case_count": len(candidates),
    }
    return manifest


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _command(argv: list[str], cwd: Path | None = None) -> dict[str, object]:
    try:
        result = subprocess.run(
            argv, cwd=cwd, text=True, capture_output=True, timeout=30, check=False
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": 127, "stdout": "", "stderr": str(error)}


def _text(argv: list[str], cwd: Path | None = None) -> str:
    return str(_command(argv, cwd)["stdout"])


def _first_line(argv: list[str]) -> str:
    text = _text(argv)
    return text.splitlines()[0] if text else ""


def _package_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "unknown"


def _docker_version(executable: Path, module: str) -> str:
    result = _command([str(executable), "-c", f"import {module}; print({module}.__version__)"])
    return str(result["stdout"]).splitlines()[-1] if result["stdout"] else "unknown"


def _detector_hash(repo: Path) -> str:
    path = repo / ".vendor/quality_repair/tools/quality_repair_checkers/layout_probe_check.py"
    if not path.is_file():
        return "missing"
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
