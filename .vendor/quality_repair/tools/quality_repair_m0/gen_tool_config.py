#!/usr/bin/env python3
"""Generate tool_config.json for converted quality_repair bundles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKERS_ROOT = REPO_ROOT / "tools" / "quality_repair_checkers"


def build_tool_config(bundle_dir: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    bundle = _read_json(bundle_dir / "bundle.json")
    profile = str(bundle.get("profile") or "layout")
    scene_name = str(bundle.get("scene_name") or "Solution")
    checkers_root = repo_root / "tools" / "quality_repair_checkers"
    if profile == "layout":
        check_cmd = [
            sys.executable,
            str(checkers_root / "layout_probe_check.py"),
            "--code",
            "{code}",
            "--workdir",
            "{workdir}",
            "--scene",
            scene_name,
        ]
    elif profile == "logic":
        check_cmd = [
            sys.executable,
            str(checkers_root / "logic_contract_check.py"),
            "--code",
            "{code}",
            "--workdir",
            "{workdir}",
        ]
    else:
        raise ValueError(f"unsupported_profile:{profile}")
    return {"check_cmd": check_cmd}


def write_tool_config(bundle_dir: Path, *, repo_root: Path = REPO_ROOT) -> Path:
    payload = build_tool_config(bundle_dir, repo_root=repo_root)
    path = bundle_dir / "tool_config.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def generate_for_root(root: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    written: list[str] = []
    skipped: list[dict[str, str]] = []
    for bundle_json in sorted(root.rglob("bundle.json")):
        bundle_dir = bundle_json.parent
        try:
            written.append(str(write_tool_config(bundle_dir, repo_root=repo_root)))
        except Exception as exc:  # noqa: BLE001 - batch summary must continue.
            skipped.append({"bundle": str(bundle_dir), "reason": str(exc)})
    return {"written_count": len(written), "skipped_count": len(skipped), "written": written, "skipped": skipped}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json_root_not_object:{path}")
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate tool_config.json for quality_repair bundles.")
    parser.add_argument("--root", required=True, type=Path, help="Bundle root containing bundle.json files.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root for checker script paths.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = generate_for_root(args.root, repo_root=args.repo_root.resolve())
    json.dump(summary, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
