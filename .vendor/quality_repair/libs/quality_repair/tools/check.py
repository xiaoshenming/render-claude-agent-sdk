from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..interfaces import CheckerAdapter
from ..schemas import CheckResult

CHECK_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class CommandTemplate:
    argv: list[str]
    reasons: list[str]


@dataclass(frozen=True, kw_only=True)
class CheckCommandRequest:
    code_path: Path
    workdir: Path
    timeout: float = CHECK_TIMEOUT_SECONDS


def _failure(error: str) -> CheckResult:
    result = CheckResult.failure(error)
    result.raw = {"reasons": [error]}
    return result


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
    value = payload.get("check_cmd")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, "missing_or_invalid_check_cmd"
    return CommandTemplate(argv=list(value), reasons=["loaded_check_cmd"]), None


def _substitute(template: CommandTemplate, request: CheckCommandRequest) -> list[str]:
    replacements = {
        "{code}": str(request.code_path),
        "{workdir}": str(request.workdir),
    }
    argv: list[str] = []
    for item in template.argv:
        rendered = item
        for key, value in replacements.items():
            rendered = rendered.replace(key, value)
        argv.append(rendered)
    return argv


def _coerce_blocking_count(payload: dict[str, Any]) -> int | None:
    for key in ("blocking_count", "blocking"):
        if key in payload and not isinstance(payload[key], bool):
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                return None
    pairs = payload.get("blocking_pairs")
    if isinstance(pairs, list):
        return len(pairs)
    return None


def _coerce_issues(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    return [item if isinstance(item, dict) else {"value": item} for item in value]


def _parse_stdout(stdout: str, returncode: int) -> CheckResult:
    text = stdout.strip()
    if not text:
        return _failure("empty_check_stdout")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return _failure(f"invalid_check_json:{exc}")
    if not isinstance(payload, dict):
        return _failure("invalid_check_json:root_not_object")
    blocking_count = _coerce_blocking_count(payload)
    if blocking_count is None:
        return _failure("invalid_check_json:missing_blocking_count")
    issues = _coerce_issues(payload.get("issues", []))
    if issues is None:
        return _failure("invalid_check_json:issues_not_list")
    raw = dict(payload)
    raw["returncode"] = returncode
    raw["reasons"] = ["parsed_checker_stdout"]
    if payload.get("ok") is False:
        error = str(payload.get("error") or "checker_not_ok")
        return CheckResult(
            ok=False,
            passed=False,
            blocking_count=blocking_count,
            issues=issues,
            raw=raw,
            error=error,
        )
    passed = payload.get("passed", blocking_count == 0)
    return CheckResult(
        ok=True,
        passed=bool(passed),
        blocking_count=blocking_count,
        issues=issues,
        raw=raw,
    )


def run_check_command(
    *,
    code_path: Path,
    workdir: Path,
    timeout: float = CHECK_TIMEOUT_SECONDS,
) -> CheckResult:
    request = CheckCommandRequest(code_path=code_path, workdir=workdir, timeout=timeout)
    template, error = _load_template(request.workdir)
    if error or template is None:
        return _failure(error or "missing_check_cmd")
    argv = _substitute(template, request)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=request.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failure("check_timeout")
    except Exception as exc:
        return _failure(f"check_command_error:{exc}")
    return _parse_stdout(completed.stdout, completed.returncode)


class SubprocessChecker(CheckerAdapter):
    def __init__(self, *, timeout: float = CHECK_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def run_check(self, code_path: Path, workdir: Path) -> CheckResult:
        return run_check_command(code_path=code_path, workdir=workdir, timeout=self._timeout)


def _cli_payload(argv: list[str] | None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--workdir")
    parser.add_argument("--code")
    parser.add_argument("--timeout", default=str(CHECK_TIMEOUT_SECONDS))
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        return {"ok": False, "error": f"unknown_args:{' '.join(unknown)}"}
    if not args.workdir:
        return {"ok": False, "error": "missing_workdir"}
    try:
        timeout = float(args.timeout)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_timeout"}
    workdir = Path(args.workdir)
    code_path = Path(args.code) if args.code else workdir / "candidate.py"
    result = run_check_command(code_path=code_path, workdir=workdir, timeout=timeout)
    payload = result.to_dict()
    payload["reasons"] = list(result.raw.get("reasons", []))
    return payload


def main(argv: list[str] | None = None) -> None:
    try:
        payload = _cli_payload(argv)
    except BaseException as exc:
        payload = {"ok": False, "error": f"check_cli_error:{exc}"}
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
