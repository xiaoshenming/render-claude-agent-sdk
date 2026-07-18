"""Runtime boundary for static logic-contract checking."""

from __future__ import annotations

import py_compile
from pathlib import Path
from typing import Any

from .loader import extract_geometry, load_contract
from .validator import validate_contract


def run_check(*, code_path: Path, workdir: Path) -> dict[str, Any]:
    compile_error = _compile_error(code_path)
    if compile_error:
        return _error_payload(f"compile_error:{compile_error}")
    contract = load_contract(workdir)
    if not contract:
        return _error_payload("missing_logic_contract")
    try:
        source = code_path.read_text(encoding="utf-8")
        geometry = extract_geometry(source, str(contract.get("scene_name") or ""))
        issues = validate_contract(contract, geometry, source)
    except Exception as exc:  # noqa: BLE001 - checker boundary
        return _error_payload(f"logic_check_error:{exc}")
    return {
        "ok": True,
        "passed": not issues,
        "blocking_count": len(issues),
        "issues": issues,
        "raw": {"point_count": len(geometry.points), "line_segment_count": len(geometry.line_segments)},
    }


def _compile_error(code_path: Path) -> str | None:
    try:
        py_compile.compile(str(code_path), doraise=True)
    except py_compile.PyCompileError as exc:
        return str(exc)
    return None


def _error_payload(error: str) -> dict[str, Any]:
    return {"ok": False, "passed": False, "blocking_count": -1, "issues": [], "error": error}
