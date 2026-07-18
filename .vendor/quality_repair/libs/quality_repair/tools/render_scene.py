from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..interfaces import RendererAdapter
from ..schemas import CheckResult
from .frame_at import FRAME_TIMEOUT_SECONDS, frame_at as run_frame_at

RENDER_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True, kw_only=True)
class RenderCommandRequest:
    code_path: Path
    scene_name: str
    out_dir: Path
    workdir: Path
    timeout: float = RENDER_TIMEOUT_SECONDS


@dataclass(frozen=True, kw_only=True)
class CommandTemplate:
    argv: list[str]
    reasons: list[str]


def _tool_result(
    *,
    ok: bool,
    out: Path | None,
    error: str | None,
    reasons: list[str],
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "out": str(out) if out is not None else None,
        "error": error,
        "reasons": reasons,
        "stdout": stdout,
        "stderr": stderr,
        "returncode": returncode,
    }


def _load_template(workdir: Path) -> tuple[CommandTemplate | None, str | None]:
    config_path = workdir / "tool_config.json"
    if not config_path.exists():
        return None, f"missing_tool_config:{config_path}"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid_tool_config:{exc}"
    if not isinstance(payload, dict):
        return None, "invalid_tool_config:root_not_object"
    value = payload.get("render_cmd")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, "missing_or_invalid_render_cmd"
    return CommandTemplate(argv=list(value), reasons=["loaded_render_cmd"]), None


def _substitute(template: CommandTemplate, request: RenderCommandRequest) -> list[str]:
    replacements = {
        "{code}": str(request.code_path),
        "{workdir}": str(request.workdir),
        "{scene}": request.scene_name,
        "{out}": str(request.out_dir),
    }
    argv: list[str] = []
    for item in template.argv:
        rendered = item
        for key, value in replacements.items():
            rendered = rendered.replace(key, value)
        argv.append(rendered)
    return argv


def render_scene(
    *,
    code_path: Path,
    scene_name: str,
    out_dir: Path,
    workdir: Path,
    timeout: float = RENDER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    request = RenderCommandRequest(
        code_path=code_path,
        scene_name=scene_name,
        out_dir=out_dir,
        workdir=workdir,
        timeout=timeout,
    )
    template, error = _load_template(request.workdir)
    if error or template is None:
        return _tool_result(ok=False, out=None, error=error, reasons=[error or "missing_render_cmd"])
    argv = _substitute(template, request)
    try:
        request.out_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=request.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _tool_result(ok=False, out=None, error="render_timeout", reasons=["render_timeout"])
    except Exception as exc:
        error_text = f"render_command_error:{exc}"
        return _tool_result(ok=False, out=None, error=error_text, reasons=[error_text])
    ok = completed.returncode == 0
    error_text = None if ok else f"render_command_failed:{completed.returncode}"
    return _tool_result(
        ok=ok,
        out=request.out_dir if ok else None,
        error=error_text,
        reasons=template.reasons + ["render_command_completed" if ok else "render_command_failed"],
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _check_result_from_tool_result(result: dict[str, Any]) -> CheckResult:
    if result.get("ok") is True:
        return CheckResult(ok=True, passed=True, blocking_count=0, raw=dict(result))
    return CheckResult(
        ok=False,
        passed=False,
        blocking_count=-1,
        raw=dict(result),
        error=str(result.get("error") or "render_failed"),
    )


class SubprocessRenderer(RendererAdapter):
    def __init__(
        self,
        *,
        workdir: Path | None = None,
        render_timeout: float = RENDER_TIMEOUT_SECONDS,
        frame_timeout: float = FRAME_TIMEOUT_SECONDS,
    ) -> None:
        self._workdir = workdir
        self._render_timeout = render_timeout
        self._frame_timeout = frame_timeout

    def render_scene(self, code_path: Path, scene_name: str, out_dir: Path) -> CheckResult:
        workdir = self._workdir or code_path.parent
        result = render_scene(
            code_path=code_path,
            scene_name=scene_name,
            out_dir=out_dir,
            workdir=workdir,
            timeout=self._render_timeout,
        )
        return _check_result_from_tool_result(result)

    def frame_at(self, video_path: Path, second: float, out_path: Path) -> Path | None:
        workdir = self._workdir or video_path.parent
        result = run_frame_at(
            video_path=video_path,
            second=second,
            out_path=out_path,
            workdir=workdir,
            timeout=self._frame_timeout,
        )
        return out_path if result.get("ok") is True else None


def _cli_payload(argv: list[str] | None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--workdir")
    parser.add_argument("--code")
    parser.add_argument("--scene", default="Scene")
    parser.add_argument("--out")
    parser.add_argument("--timeout", default=str(RENDER_TIMEOUT_SECONDS))
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        return _tool_result(ok=False, out=None, error=f"unknown_args:{' '.join(unknown)}", reasons=[])
    if not args.workdir:
        return _tool_result(ok=False, out=None, error="missing_workdir", reasons=["missing_workdir"])
    try:
        timeout = float(args.timeout)
    except (TypeError, ValueError):
        return _tool_result(ok=False, out=None, error="invalid_timeout", reasons=["invalid_timeout"])
    workdir = Path(args.workdir)
    code_path = Path(args.code) if args.code else workdir / "candidate.py"
    out_dir = Path(args.out) if args.out else workdir / "render_out"
    return render_scene(
        code_path=code_path,
        scene_name=str(args.scene),
        out_dir=out_dir,
        workdir=workdir,
        timeout=timeout,
    )


def main(argv: list[str] | None = None) -> None:
    try:
        payload = _cli_payload(argv)
    except BaseException as exc:
        payload = _tool_result(ok=False, out=None, error=f"render_cli_error:{exc}", reasons=["render_cli_error"])
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
