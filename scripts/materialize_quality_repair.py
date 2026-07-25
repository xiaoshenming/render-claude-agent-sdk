"""Materialize the verified overlap vendor into an ignored local directory."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from vendor_verification import BASELINES
from vendor_verification.archive import inspect_quality_archive

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = (
    ROOT
    / "vendor"
    / "source_archives"
    / "quality_repair_source_handoff_20260711_platform1.tar.gz"
)
DEFAULT_TARGET = ROOT / ".vendor" / "quality_repair"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    return parser.parse_args()


def _ensure_empty_target(target: Path) -> None:
    if not target.exists():
        return
    if not target.is_dir() or any(target.iterdir()):
        raise ValueError(f"target must be absent or empty: {target}")


def materialize(archive: Path, target: Path) -> None:
    """Verify ``archive`` and atomically create a prefix-stripped vendor tree."""
    target = target.resolve()
    _ensure_empty_target(target)
    issues, files = inspect_quality_archive(archive, BASELINES["quality_repair"])
    if issues:
        raise ValueError("; ".join(issues))

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="quality-repair-", dir=target.parent))
    try:
        for relative, payload in sorted(files.items()):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        if target.exists():
            target.rmdir()
        staging.replace(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    args = _parse_args()
    try:
        materialize(args.archive, args.target)
    except (OSError, ValueError) as error:
        print(f"quality_repair materialization failed: {error}", file=sys.stderr)
        return 1
    print(f"quality_repair materialized: {args.target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
