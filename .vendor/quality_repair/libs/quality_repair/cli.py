"""Command line entrypoint for local quality_repair bundle replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .api import RepairBundle, RepairResult, repair
from .interfaces import ToolBox
from .tools.check import SubprocessChecker
from .tools.solve_layout import AxialSolver


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quality_repair")
    parser.add_argument("--bundle", required=True, help="case directory with candidate.py")
    args = parser.parse_args(argv)
    try:
        bundle = _bundle_from_dir(Path(args.bundle))
        result = repair(
            bundle,
            ToolBox(checker=SubprocessChecker(), solver=AxialSolver()),
        )
        print(json.dumps(_result_payload(result), ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI must print structured JSON
        print(json.dumps({"status": "REVIEW_ERROR", "error": str(exc)}, ensure_ascii=False), flush=True)
        return 0


def _bundle_from_dir(bundle_dir: Path) -> RepairBundle:
    config = _read_config(bundle_dir / "bundle.json")
    code_path = _resolve(bundle_dir, config.get("code_path"), "candidate.py")
    return RepairBundle(
        job_id=str(config.get("job_id") or bundle_dir.name),
        code_path=code_path,
        profile=str(config.get("profile") or "layout"),
        layout_context=_optional_path(bundle_dir, config.get("layout_context"), "layout_context.json"),
        logic_contract=_optional_path(bundle_dir, config.get("logic_contract"), "logic_contract.json"),
        source_region=_optional_path(bundle_dir, config.get("source_region"), "source_region.md"),
        render_artifacts=_optional_path(bundle_dir, config.get("render_artifacts"), "render_artifacts"),
        frames=_frame_paths(bundle_dir, config.get("frames")),
        evidence_root=_optional_path(bundle_dir, config.get("evidence_root"), "evidence"),
    )


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _resolve(base: Path, value: Any, default_name: str) -> Path:
    if not value:
        return base / default_name
    raw = Path(str(value))
    return raw if raw.is_absolute() else base / raw


def _optional_path(base: Path, value: Any, default_name: str) -> Path | None:
    path = _resolve(base, value, default_name)
    return path if path.exists() else None


def _frame_paths(base: Path, value: Any) -> list[Path]:
    if isinstance(value, list):
        return [_resolve(base, item, "") for item in value]
    frames_dir = base / "frames"
    if frames_dir.is_dir():
        return sorted(path for path in frames_dir.iterdir() if path.is_file())
    return []


def _result_payload(result: RepairResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "code_path": str(result.code_path),
        "repairability": result.repairability,
        "before": dict(result.before),
        "after": dict(result.after),
        "rounds_used": result.rounds_used,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "evidence_dir": str(result.evidence_dir) if result.evidence_dir else None,
        "reasons": list(result.reasons),
    }


if __name__ == "__main__":
    raise SystemExit(main())
