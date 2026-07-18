from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FRAME_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class FrameCommandRequest:
    video_path: Path
    second: float
    out_path: Path
    workdir: Path
    timeout: float = FRAME_TIMEOUT_SECONDS


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
    value = payload.get("frame_cmd")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, "missing_or_invalid_frame_cmd"
    return CommandTemplate(argv=list(value), reasons=["loaded_frame_cmd"]), None


def _substitute(template: CommandTemplate, request: FrameCommandRequest) -> list[str]:
    replacements = {
        "{workdir}": str(request.workdir),
        "{video}": str(request.video_path),
        "{second}": str(request.second),
        "{out}": str(request.out_path),
    }
    argv: list[str] = []
    for item in template.argv:
        rendered = item
        for key, value in replacements.items():
            rendered = rendered.replace(key, value)
        argv.append(rendered)
    return argv


def frame_at(
    *,
    video_path: Path,
    second: float,
    out_path: Path,
    workdir: Path,
    timeout: float = FRAME_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    request = FrameCommandRequest(
        video_path=video_path,
        second=second,
        out_path=out_path,
        workdir=workdir,
        timeout=timeout,
    )
    template, error = _load_template(request.workdir)
    if error or template is None:
        return _tool_result(ok=False, out=None, error=error, reasons=[error or "missing_frame_cmd"])
    argv = _substitute(template, request)
    try:
        request.out_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=request.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _tool_result(ok=False, out=None, error="frame_timeout", reasons=["frame_timeout"])
    except Exception as exc:
        error_text = f"frame_command_error:{exc}"
        return _tool_result(ok=False, out=None, error=error_text, reasons=[error_text])
    ok = completed.returncode == 0
    error_text = None if ok else f"frame_command_failed:{completed.returncode}"
    return _tool_result(
        ok=ok,
        out=request.out_path if ok else None,
        error=error_text,
        reasons=template.reasons + ["frame_command_completed" if ok else "frame_command_failed"],
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _cli_payload(argv: list[str] | None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--workdir")
    parser.add_argument("--video")
    parser.add_argument("--second", default="0")
    parser.add_argument("--out")
    parser.add_argument("--timeout", default=str(FRAME_TIMEOUT_SECONDS))
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        return _tool_result(ok=False, out=None, error=f"unknown_args:{' '.join(unknown)}", reasons=[])
    if not args.workdir:
        return _tool_result(ok=False, out=None, error="missing_workdir", reasons=["missing_workdir"])
    try:
        second = float(args.second)
        timeout = float(args.timeout)
    except (TypeError, ValueError):
        return _tool_result(ok=False, out=None, error="invalid_number", reasons=["invalid_number"])
    workdir = Path(args.workdir)
    video_path = Path(args.video) if args.video else workdir / "video.mp4"
    out_path = Path(args.out) if args.out else workdir / "frame.png"
    return frame_at(video_path=video_path, second=second, out_path=out_path, workdir=workdir, timeout=timeout)


def main(argv: list[str] | None = None) -> None:
    try:
        payload = _cli_payload(argv)
    except BaseException as exc:
        payload = _tool_result(ok=False, out=None, error=f"frame_cli_error:{exc}", reasons=["frame_cli_error"])
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
