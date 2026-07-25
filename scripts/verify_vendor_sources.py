"""Verify frozen source identities, manifests, provenance, and inventory."""

import argparse
import sys
from pathlib import Path

from vendor_verification import verify_workspace


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--quality-archive", type=Path, help="optional original source archive"
    )
    return parser.parse_args()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = _parse_args()
    issues = verify_workspace(args.root.resolve(), args.quality_archive)
    if issues:
        print("Vendor source verification: FAIL")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Vendor source verification: PASS")
    print("- quality_repair: metadata and 116 payload files verified")
    print("- logic_self_audit_baseline: identity and 14 files verified")
    print("- logic_engine_mvp_baseline: identity and 33 payload files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
