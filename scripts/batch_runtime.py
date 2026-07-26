"""Batch preflight and comparable runtime manifest."""

from __future__ import annotations

import ast
import json
import os
import platform
import subprocess
from pathlib import Path

import httpx


def preflight(args, candidates: list[Path]) -> dict[str, object]:
    image = os.environ.get("MANIM_DOCKER_IMAGE", "docker-manim-worker-1:latest")
    image_id = _command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    provider_smoke = _provider_tool_smoke(args.model)
    issues = [
        *_credential_issues(),
        *_path_issues(args),
        *_candidate_issues(candidates),
        *_binary_issues(image, image_id),
        *_import_issues(args),
    ]
    if not provider_smoke["ok"]:
        issues.append(f"provider tool smoke failed: {provider_smoke['error']}")
    return {
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
        "provider_tool_smoke": provider_smoke,
    }


def _credential_issues() -> list[str]:
    for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        if os.environ.get(name, "").strip():
            return []
    return ["provider authentication missing"]


def _path_issues(args) -> list[str]:
    return [
        f"{label} missing: {path}"
        for path, label in (
            (args.manim_python, "manim python"),
            (args.runtime_python_path, "runtime python path"),
        )
        if not Path(path).exists()
    ]


def _candidate_issues(candidates: list[Path]) -> list[str]:
    issues: list[str] = []
    for candidate in candidates:
        try:
            source = candidate.read_text(encoding="utf-8")
            ast.parse(source)
            compile(source, str(candidate), "exec")
        except Exception as error:
            issues.append(f"candidate invalid: {candidate}: {error}")
    return issues


def _binary_issues(image: str, image_id: dict[str, object]) -> list[str]:
    issues: list[str] = []
    docker = _command(["docker", "info", "--format", "{{.ServerVersion}}"])
    if docker["returncode"] != 0:
        issues.append("docker daemon unavailable")
    if image_id["returncode"] != 0:
        issues.append(f"docker image unavailable: {image}")
    for command in ("ffmpeg", "ffprobe"):
        check = _command([command, "-version"])
        if check["returncode"] != 0:
            issues.append(f"{command} unavailable")
    return issues


def _import_issues(args) -> list[str]:
    issues: list[str] = []
    import_check = _command(
        [os.environ.get("PYTHON", "python"), "-c", "import manim_quality.operator"],
        cwd=args.repo,
        env=_python_environment(args.repo),
    )
    if import_check["returncode"] != 0:
        issues.append("manim_quality.operator import failed")
    render_import = _command(
        [
            str(args.manim_python),
            "-c",
            (
                "from custom_services.system_tts_service "
                "import create_system_tts_service"
            ),
        ],
        cwd=args.repo,
        env=_render_environment(args.runtime_python_path),
    )
    if render_import["returncode"] != 0:
        issues.append("render runtime stubs import failed")
    return issues


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _command(
    argv: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
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


def _python_environment(repo: Path) -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str((repo / "src").resolve())
    inherited = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        source_root if not inherited else os.pathsep.join((source_root, inherited))
    )
    return environment


def _render_environment(runtime_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(runtime_path).resolve())
    return environment


def _provider_tool_smoke(model: str) -> dict[str, object]:
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not key:
        return {"ok": False, "error": "authentication missing"}
    payload = {
        "model": model,
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "Call the health tool once."}],
        "tools": [
            {
                "name": "health",
                "description": "Return runtime health.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ],
        "tool_choice": {"type": "tool", "name": "health"},
    }
    try:
        response = httpx.post(
            f"{base}/v1/messages",
            headers={
                "x-api-key": key,
                "authorization": f"Bearer {key}",
                "anthropic-version": "2023-06-01",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        value = response.json()
        content = value.get("content") if isinstance(value, dict) else None
        used = any(
            isinstance(item, dict) and item.get("type") == "tool_use"
            for item in (content or [])
        )
        usage = value.get("usage") if isinstance(value, dict) else None
        return {"ok": used, "error": None if used else "tool_use missing", "usage": usage}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {str(error)[:300]}"}
