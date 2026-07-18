#!/usr/bin/env python3
"""Build compact overlap layout_context.json for Claude SDK repair runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from libs.quality_repair.contract.build_workdir import _audit_layout_context_for_agent


def build_layout_context(check_result: dict[str, Any], probe_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the audit-compatible compact context consumed by layout repair agents."""
    probe = probe_result if isinstance(probe_result, dict) else {}
    embedded_probe = check_result.get("layout_probe")
    if not probe and isinstance(embedded_probe, dict):
        probe = embedded_probe

    issues = _issues_from_check(check_result)
    blocking_count = _blocking_count_from_check(check_result, issues)
    layout_ctx: dict[str, Any] = {
        "active_visible_objects": _visible_objects(probe, check_result),
        "blocking_layout_issue_count": blocking_count,
        "pass": _pass_from_check(check_result, blocking_count),
        "status": _status_from_check(check_result, blocking_count),
        "collisions": issues,
    }
    summary = check_result.get("summary")
    if isinstance(summary, str) and summary:
        layout_ctx["summary"] = summary
    return _audit_layout_context_for_agent(layout_ctx)


def build_layout_context_from_files(check_result_path: Path, probe_result_path: Path | None = None) -> dict[str, Any]:
    check_result = _read_json(check_result_path)
    probe_result = _read_json(probe_result_path) if probe_result_path else None
    return build_layout_context(check_result, probe_result)


def _issues_from_check(check_result: dict[str, Any]) -> list[Any]:
    for key in ("blocking_layout_issues", "issues", "top_blocking_issues", "collisions"):
        value = check_result.get(key)
        if isinstance(value, list):
            return value
    return []


def _blocking_count_from_check(check_result: dict[str, Any], issues: list[Any]) -> int:
    for key in ("blocking_layout_issue_count", "blocking_count", "blocking"):
        value = check_result.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return len(issues)


def _pass_from_check(check_result: dict[str, Any], blocking_count: int) -> bool:
    for key in ("pass", "passed"):
        value = check_result.get(key)
        if isinstance(value, bool):
            return value
    return blocking_count == 0


def _status_from_check(check_result: dict[str, Any], blocking_count: int) -> str:
    value = check_result.get("status")
    if isinstance(value, str) and value:
        return value
    return "pass" if blocking_count == 0 else "layout_failed"


def _visible_objects(probe_result: dict[str, Any], check_result: dict[str, Any]) -> list[Any]:
    for source in (probe_result, check_result):
        for key in ("visible_objects", "active_visible_objects", "objects", "active_objects"):
            value = source.get(key)
            if isinstance(value, list):
                return value
    return []


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _run_probe_and_build(args: argparse.Namespace) -> dict[str, Any]:
    from tools.quality_repair_checkers.layout_probe_check import run_check

    check_result = run_check(
        code_path=args.code,
        workdir=args.workdir,
        scene_name=args.scene,
        timeout=args.timeout,
    )
    probe_path = args.workdir / "layout_probe_check" / "layout_probe.json"
    probe_result = _read_json(probe_path) if probe_path.exists() else {}
    return build_layout_context(check_result, probe_result)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build compact layout_context.json for overlap repair.")
    parser.add_argument("--check-result", type=Path, help="Existing check_result.json.")
    parser.add_argument("--probe-result", type=Path, help="Existing layout_probe.json.")
    parser.add_argument("--code", type=Path, help="candidate.py to probe when --check-result is omitted.")
    parser.add_argument("--workdir", type=Path, help="Working directory for live probe mode.")
    parser.add_argument("--scene", help="Scene class name for live probe mode.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--out", type=Path, help="Where to write layout_context.json.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.check_result:
            context = build_layout_context_from_files(args.check_result, args.probe_result)
        else:
            missing = [
                name
                for name, value in (("--code", args.code), ("--workdir", args.workdir), ("--scene", args.scene))
                if not value
            ]
            if missing:
                raise ValueError("missing live probe arguments: " + ", ".join(missing))
            context = _run_probe_and_build(args)
        if args.out:
            _write_json(args.out, context)
        print(json.dumps(context, ensure_ascii=False, default=str), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI must emit machine-readable failure
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
