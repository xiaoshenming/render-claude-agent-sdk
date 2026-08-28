"""Build a git-pinned SDK release that includes the verified ignored vendor."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

VENDOR = Path(".vendor/quality_repair")
REQUIRED_VENDOR = (
    Path("PAYLOAD_SHA256SUMS.txt"),
    Path("tools/quality_repair_checkers/layout_probe_check.py"),
)


def build_release_bundle(source: Path, output: Path, commit: str) -> dict[str, object]:
    source = source.resolve(strict=True)
    _require_commit(source, commit)
    vendor = source / VENDOR
    vendor_files = _verify_vendor(vendor)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="quality-agent-release-") as raw:
        staging = Path(raw) / "release"
        staging.mkdir()
        _extract_git_archive(source, commit, staging)
        shutil.copytree(
            vendor,
            staging / VENDOR,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        (staging / "RELEASE_COMMIT").write_text(commit + "\n", encoding="utf-8")
        with tarfile.open(output, "w:gz") as archive:
            for path in sorted(staging.rglob("*")):
                archive.add(path, arcname=path.relative_to(staging), recursive=False)
    receipt = verify_release_bundle(output, commit)
    if receipt["vendor_files"] != vendor_files:
        raise ValueError("release vendor inventory changed during packaging")
    return receipt


def verify_release_bundle(path: Path, commit: str) -> dict[str, object]:
    required = {
        "RELEASE_COMMIT",
        "QUALITY_AGENT_ABI",
        *(str(VENDOR / value) for value in REQUIRED_VENDOR),
    }
    with tarfile.open(path, "r:gz") as archive:
        members = {item.name: item for item in archive.getmembers() if item.isfile()}
        missing = sorted(required - members.keys())
        if missing:
            raise ValueError(f"release bundle missing required files: {missing}")
        marker = archive.extractfile(members["RELEASE_COMMIT"])
        if marker is None or marker.read().decode().strip() != commit:
            raise ValueError("release bundle commit marker mismatch")
        vendor_files = sum(name.startswith(f"{VENDOR}/") for name in members)
    return {
        "path": str(path.resolve()),
        "commit": commit,
        "sha256": _sha256(path),
        "vendor_files": vendor_files,
    }


def _require_commit(source: Path, commit: str) -> None:
    resolved = subprocess.check_output(
        ["git", "rev-parse", commit], cwd=source, text=True
    ).strip()
    if resolved != commit:
        raise ValueError("commit must be a full canonical Git SHA")


def _verify_vendor(root: Path) -> int:
    for relative in REQUIRED_VENDOR:
        if not (root / relative).is_file():
            raise ValueError(f"materialized vendor missing: {relative}")
    lines = (root / "PAYLOAD_SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    for line in lines:
        expected, relative = line.split("  ", 1)
        target = (root / relative).resolve(strict=True)
        if root.resolve() not in target.parents or target.is_symlink():
            raise ValueError(f"unsafe vendor payload path: {relative}")
        if _sha256(target) != expected:
            raise ValueError(f"vendor payload hash mismatch: {relative}")
    return sum(
        path.is_file()
        for path in root.rglob("*")
        if "__pycache__" not in path.parts
    )


def _extract_git_archive(source: Path, commit: str, target: Path) -> None:
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", commit], cwd=source, stdout=subprocess.PIPE
    )
    if process.stdout is None:
        raise RuntimeError("git archive stdout is unavailable")
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        archive.extractall(target, filter="data")
    if process.wait() != 0:
        raise RuntimeError("git archive failed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit")
    args = parser.parse_args()
    commit = args.commit or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.source, text=True
    ).strip()
    print(build_release_bundle(args.source, args.output, commit))


if __name__ == "__main__":
    main()
