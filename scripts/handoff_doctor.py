"""Verify every dependency required by the bundled end-to-end harness."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument("--require-api-key", action="store_true")
    return parser.parse_args()


def _record(checks: list[dict[str, object]], name: str, passed: bool, detail: str):
    checks.append({"name": name, "passed": passed, "detail": detail})


def _required_files(checks: list[dict[str, object]]) -> None:
    paths = (
        "src/manim_quality/__init__.py",
        "evals/run_workbench_e2e.py",
        "evals/workbench_e2e/job_runner.py",
        "external/layout_probe/probe_runner.py",
        ".vendor/quality_repair/PAYLOAD_SHA256SUMS.txt",
        "vendor/logic_engine_mvp_baseline/SOURCE_MANIFEST.sha256",
        "handoff_data/prompts_minimal.sqlite3",
        "handoff_data/workload_v1.json",
    )
    for relative in paths:
        path = ROOT / relative
        _record(checks, f"file:{relative}", path.is_file(), str(path))


def _python_imports(checks: list[dict[str, object]]) -> None:
    for path in (ROOT / "src", ROOT, ROOT / "vendor/logic_engine_mvp_baseline"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    try:
        from tools.logic_engine_mvp.logic_engine_mvp.logic_facts import (
            extract_deterministic_logic_facts,
        )

        import manim_quality  # noqa: F401
        from evals.workbench_e2e.job_runner import run_job  # noqa: F401
        from manim_quality.layout import MaterializedQualityRepair

        extract_deterministic_logic_facts("from manim import *\n")
        MaterializedQualityRepair(ROOT / ".vendor/quality_repair")
    except Exception as error:
        _record(
            checks,
            "python-imports-and-vendors",
            False,
            f"{type(error).__name__}:{error}",
        )
    else:
        _record(
            checks,
            "python-imports-and-vendors",
            True,
            "imports and payload hashes verified",
        )


def _probe(checks: list[dict[str, object]]) -> None:
    path = ROOT / "external/layout_probe/probe_runner.py"
    try:
        spec = importlib.util.spec_from_file_location("handoff_layout_probe", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot create module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = getattr(module, "PROBE_RUNNER_SOURCE", None)
        if not isinstance(source, str) or "def main(" not in source:
            raise ValueError("PROBE_RUNNER_SOURCE is invalid")
    except Exception as error:
        _record(checks, "layout-probe", False, f"{type(error).__name__}:{error}")
    else:
        _record(checks, "layout-probe", True, f"embedded source chars={len(source)}")


def _prompt_database(checks: list[dict[str, object]]) -> None:
    path = ROOT / "handoff_data/prompts_minimal.sqlite3"
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "select prompt_id, max(version_number) from prompt_versions "
                "group by prompt_id order by prompt_id"
            ).fetchall()
        if rows != [(95, 1), (98, 1), (99, 1)]:
            raise ValueError(f"unexpected prompt rows: {rows}")
    except Exception as error:
        _record(
            checks,
            "minimal-prompt-database",
            False,
            f"{type(error).__name__}:{error}",
        )
    else:
        _record(checks, "minimal-prompt-database", True, "prompt ids 95, 98, 99")


def _manim(checks: list[dict[str, object]], python: Path) -> None:
    if not python.is_file():
        _record(checks, "manim-python", False, f"missing: {python}")
        return
    try:
        result = subprocess.run(
            [str(python), "-m", "manim", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except Exception as error:
        _record(checks, "manim-python", False, f"{type(error).__name__}:{error}")
        return
    text = (result.stdout or result.stderr).strip().splitlines()
    detail = text[-1] if text else f"returncode={result.returncode}"
    _record(checks, "manim-python", result.returncode == 0, detail)


def _api_key(checks: list[dict[str, object]], required: bool) -> None:
    names = (
        "MANIM_QUALITY_API_KEY",
        "MANIM_E2E_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
    )
    present = [name for name in names if os.environ.get(name, "").strip()]
    _record(
        checks,
        "model-api-key",
        bool(present) or not required,
        (
            "configured via " + present[0]
            if present
            else "not configured (value never printed)"
        ),
    )


def main() -> int:
    args = _arguments()
    checks: list[dict[str, object]] = []
    version_ok = sys.version_info[:2] in {(3, 11), (3, 12)}
    _record(checks, "platform-python", version_ok, sys.version.split()[0])
    _required_files(checks)
    _python_imports(checks)
    _probe(checks)
    _prompt_database(checks)
    _manim(checks, args.manim_python.absolute())
    _api_key(checks, args.require_api_key)
    passed = all(bool(item["passed"]) for item in checks)
    payload = {"schema_version": 1, "passed": passed, "checks": checks}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
