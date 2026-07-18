"""Inspect the frozen overlap archive without adding it to the active source tree."""

from __future__ import annotations

import hashlib
import stat
import tarfile
from pathlib import Path, PurePosixPath


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(reparse_flag and attributes & reparse_flag)


def _relative_member(name: str, prefix: str) -> str | None:
    if "\\" in name:
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    if path.parts[0] != prefix:
        return None
    if len(path.parts) == 1:
        return ""
    return PurePosixPath(*path.parts[1:]).as_posix()


def _read_files(
    archive: Path,
    prefix: str,
    issues: list[str],
) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        bundle = tarfile.open(archive, "r:gz")
    except (OSError, tarfile.TarError) as error:
        issues.append(f"invalid quality_repair archive: {error}")
        return files
    with bundle:
        for member in bundle.getmembers():
            relative = _relative_member(member.name, prefix)
            if relative is None:
                issues.append(f"unsafe archive member: {member.name}")
                continue
            if not relative:
                if not member.isdir():
                    issues.append(f"unsupported archive member: {member.name}")
                continue
            if member.isdir():
                continue
            if not member.isfile() or member.issym() or member.islnk():
                issues.append(f"unsupported archive member: {member.name}")
                continue
            if relative in files:
                issues.append(f"duplicate archive member: {relative}")
                continue
            extracted = bundle.extractfile(member)
            if extracted is None:
                issues.append(f"unreadable archive member: {relative}")
                continue
            files[relative] = extracted.read()
    return files


def _parse_hash_manifest(data: bytes, issues: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        issues.append("invalid UTF-8 hash manifest in quality_repair archive")
        return entries
    for line_number, line in enumerate(lines, start=1):
        digest, separator, relative = line.partition("  ")
        path = PurePosixPath(relative)
        valid_digest = len(digest) == 64 and all(
            char in "0123456789abcdef" for char in digest
        )
        valid_path = (
            bool(relative)
            and not path.is_absolute()
            and ".." not in path.parts
            and "\\" not in relative
        )
        if not separator or not valid_digest or not valid_path:
            issues.append(f"invalid archive manifest line: {line_number}")
        elif relative in entries:
            issues.append(f"duplicate archive manifest path: {relative}")
        else:
            entries[relative] = digest
    return entries


def _verify_payload_manifest(
    files: dict[str, bytes],
    config: dict[str, object],
    issues: list[str],
) -> dict[str, str]:
    manifest_name = str(config["manifest_path"])
    manifest = files.get(manifest_name)
    if manifest is None:
        issues.append(f"missing archive manifest: {manifest_name}")
        return {}
    if _sha256_bytes(manifest) != str(config["manifest_sha256"]):
        issues.append(f"hash mismatch: {manifest_name}")
    return _parse_hash_manifest(manifest, issues)


def _verify_payload_files(
    files: dict[str, bytes],
    entries: dict[str, str],
    config: dict[str, object],
    issues: list[str],
) -> None:
    expected_files = set(entries).union(config["metadata_files"])
    for relative in sorted(expected_files - set(files)):
        issues.append(f"missing archive file: {relative}")
    for relative in sorted(set(files) - expected_files):
        issues.append(f"unexpected archive file: {relative}")
    for relative, expected in entries.items():
        if relative in files and _sha256_bytes(files[relative]) != expected:
            issues.append(f"hash mismatch: archive payload {relative}")
    for relative in config["required_files"]:
        if relative not in files:
            issues.append(f"missing required archive file: {relative}")


def _verify_inventory_manifest(
    files: dict[str, bytes],
    entries: dict[str, str],
    config: dict[str, object],
    issues: list[str],
) -> None:
    inventory_name = str(config["inventory_manifest_path"])
    inventory = files.get(inventory_name)
    if inventory is None:
        issues.append(f"missing archive manifest: {inventory_name}")
        return
    if _sha256_bytes(inventory) != str(config["inventory_manifest_sha256"]):
        issues.append(f"hash mismatch: {inventory_name}")
    try:
        inventory_entries = set(inventory.decode("utf-8").splitlines())
    except UnicodeDecodeError:
        issues.append("invalid UTF-8 inventory manifest in quality_repair archive")
        return
    if inventory_entries != set(entries):
        issues.append("archive inventory does not match payload manifest")


def inspect_quality_archive(
    archive: Path,
    config: dict[str, object],
) -> tuple[list[str], dict[str, bytes]]:
    """Return integrity issues and the prefix-stripped verified file payload."""
    issues: list[str] = []
    if _is_link_or_reparse(archive):
        return ["quality_repair archive must not be a symlink or reparse point"], {}
    if not archive.is_file():
        return [f"missing source archive: {archive}"], {}
    expected_archive_hash = str(config["source_archive_sha256"])
    if _sha256_file(archive) != expected_archive_hash:
        issues.append("hash mismatch: quality_repair source archive")

    files = _read_files(archive, str(config["archive_prefix"]), issues)
    entries = _verify_payload_manifest(files, config, issues)
    _verify_payload_files(files, entries, config, issues)
    _verify_inventory_manifest(files, entries, config, issues)
    return sorted(issues), files
