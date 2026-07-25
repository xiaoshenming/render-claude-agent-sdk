"""Verify the immutable files in a delivered handoff package."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    manifest = root / "PACKAGE_MANIFEST.sha256"
    failures: list[str] = []
    checked = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            failures.append(f"path escapes package: {relative}")
            continue
        if not target.is_file():
            failures.append(f"missing: {relative}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(f"hash mismatch: {relative}")
        checked += 1
    if failures:
        print("\n".join(failures))
        return 1
    print(f"Package verification passed: {checked} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
