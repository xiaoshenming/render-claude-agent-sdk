#!/usr/bin/env python3
"""Convert audit demo cases into quality_repair bundle cases."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OPTIONAL_METADATA_FILES = ("case.json", "case_manifest.json")


@dataclass(frozen=True)
class CaseSource:
    input_parts: tuple[str, ...]
    output_group: str
    profile: str
    required_files: tuple[str, ...]
    rename_files: dict[str, str]


CASE_SOURCES = (
    CaseSource(
        input_parts=("overlap", "rand10_direct", "cases"),
        output_group="overlap_rand10_direct",
        profile="layout",
        required_files=("candidate.py", "layout_context.json"),
        rename_files={},
    ),
    CaseSource(
        input_parts=("overlap", "rand5_direct", "cases"),
        output_group="overlap_rand5_direct",
        profile="layout",
        required_files=("candidate.py", "layout_context.json"),
        rename_files={},
    ),
    CaseSource(
        input_parts=("logic", "auto11_contract", "cases"),
        output_group="logic_auto11_contract",
        profile="logic",
        required_files=("candidate.py", "logic_contract_context.json", "source_region.md"),
        rename_files={"logic_contract_context.json": "logic_contract.json"},
    ),
    CaseSource(
        input_parts=("logic", "hard10_experimental", "cases"),
        output_group="logic_hard10_experimental",
        profile="logic",
        required_files=("candidate.py", "logic_contract_context.json", "source_region.md"),
        rename_files={"logic_contract_context.json": "logic_contract.json"},
    ),
)


def build_bundle(case_dir: Path, source: CaseSource) -> dict[str, str]:
    bundle = {
        "job_id": case_dir.name,
        "profile": source.profile,
        "code_path": "candidate.py",
    }
    if source.profile == "layout":
        bundle["layout_context"] = "layout_context.json"
    elif source.profile == "logic":
        bundle["logic_contract"] = "logic_contract.json"
        bundle["source_region"] = "source_region.md"
    bundle["evidence_root"] = "evidence"
    scene_name = read_scene_name(case_dir)
    if scene_name:
        bundle["scene_name"] = scene_name
    return bundle


def convert_case(case_dir: Path, out_root: Path, source: CaseSource) -> dict[str, Any]:
    missing = [name for name in source.required_files if not (case_dir / name).is_file()]
    if missing:
        return {
            "converted": None,
            "skipped": {
                "source": str(case_dir),
                "output_group": source.output_group,
                "reason": "missing_required_files",
                "missing": missing,
            },
        }

    bundle_case = out_root / source.output_group / case_dir.name
    bundle_case.mkdir(parents=True, exist_ok=True)
    for file_name in source.required_files:
        output_name = source.rename_files.get(file_name, file_name)
        shutil.copy2(case_dir / file_name, bundle_case / output_name)
    for file_name in OPTIONAL_METADATA_FILES:
        source_file = case_dir / file_name
        if source_file.is_file():
            shutil.copy2(source_file, bundle_case / file_name)

    bundle_path = bundle_case / "bundle.json"
    bundle_path.write_text(
        json.dumps(build_bundle(case_dir, source), ensure_ascii=True, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return {
        "converted": {
            "source": str(case_dir),
            "output": str(bundle_case),
            "output_group": source.output_group,
            "job_id": case_dir.name,
            "profile": source.profile,
        },
        "skipped": None,
    }


def read_scene_name(case_dir: Path) -> str | None:
    for file_name in OPTIONAL_METADATA_FILES:
        path = case_dir / file_name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("scene_name"), str):
            scene_name = payload["scene_name"].strip()
            if scene_name:
                return scene_name
    return None


def convert_audit_cases(audit_root: Path, out_root: Path) -> dict[str, Any]:
    converted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    out_root.mkdir(parents=True, exist_ok=True)

    for source in CASE_SOURCES:
        cases_root = audit_root.joinpath(*source.input_parts)
        if not cases_root.is_dir():
            continue
        for case_dir in sorted(path for path in cases_root.iterdir() if path.is_dir()):
            result = convert_case(case_dir, out_root, source)
            if result["converted"] is not None:
                converted.append(result["converted"])
            if result["skipped"] is not None:
                skipped.append(result["skipped"])

    return {
        "converted_count": len(converted),
        "skipped_count": len(skipped),
        "converted": converted,
        "skipped": skipped,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert audit demo cases into quality_repair bundle cases."
    )
    parser.add_argument("--audit", required=True, type=Path, help="Audit demo root directory.")
    parser.add_argument("--out", required=True, type=Path, help="Output bundle root directory.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = convert_audit_cases(args.audit, args.out)
    json.dump(summary, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
