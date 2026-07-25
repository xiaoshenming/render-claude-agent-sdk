from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "logic_engine_mvp.freeze_manifest.v1"


def iter_source_files(source_root: Path) -> list[Path]:
    source_root = Path(source_root)
    return sorted(
        path
        for path in source_root.rglob("*.py")
        if path.is_file() and "__pycache__" not in path.parts
    )


def build_freeze_manifest(files: Iterable[Path], *, root: Path, label: str = "") -> dict[str, Any]:
    root = Path(root).resolve()
    entries = [_file_entry(Path(path), root=root) for path in files]
    entries.sort(key=lambda item: item["path"])
    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "root": str(root),
        "file_count": len(entries),
        "files": entries,
    }


def write_freeze_manifest(files: Iterable[Path], out_path: Path, *, root: Path, label: str = "") -> dict[str, Any]:
    manifest = build_freeze_manifest(files, root=root, label=label)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def verify_freeze_manifest(manifest_path: Path, *, root: Path | None = None) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check_root = Path(root or manifest["root"]).resolve()
    mismatches = []
    missing = []
    for entry in manifest.get("files") or []:
        rel_path = str(entry.get("path") or "")
        path = check_root / Path(rel_path)
        if not path.exists():
            missing.append(rel_path)
            continue
        current = _sha256(path)
        if current != entry.get("sha256"):
            mismatches.append({"path": rel_path, "expected_sha256": entry.get("sha256"), "actual_sha256": current})
    return {
        "ok": not mismatches and not missing,
        "manifest": str(manifest_path),
        "root": str(check_root),
        "checked_count": len(manifest.get("files") or []),
        "mismatch_count": len(mismatches),
        "missing_count": len(missing),
        "mismatches": mismatches,
        "missing": missing,
    }


def freeze_source_root(source_root: Path, out_path: Path, *, label: str = "") -> dict[str, Any]:
    source_root = Path(source_root)
    manifest = write_freeze_manifest(iter_source_files(source_root), out_path, root=source_root, label=label)
    return {"ok": True, "manifest": manifest, "out": str(out_path)}


def _file_entry(path: Path, *, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
