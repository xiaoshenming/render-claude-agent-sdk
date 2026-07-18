"""Offline integrity checks for frozen source baselines."""

import hashlib
import stat
from pathlib import Path, PurePosixPath

from .archive import inspect_quality_archive
from .baselines import BASELINES
from .provenance_config import NULL_PROVENANCE_VALUES, PROVENANCE_FIELDS

_IGNORED_PARTS = {".pytest_cache", "__pycache__"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in value


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(reparse_flag and attributes & reparse_flag)


def _check_regular_manifest(path: Path, display: str, issues: list[str]) -> bool:
    if _is_link_or_reparse(path):
        issues.append(f"manifest must not be a symlink or reparse point: {display}")
        return False
    if not path.is_file():
        issues.append(f"missing manifest: {display}")
        return False
    return True


def _read_hash_manifest(path: Path, issues: list[str]) -> dict[str, str]:
    if not path.is_file():
        issues.append(f"missing manifest: {path.as_posix()}")
        return {}
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        digest, separator, relative = raw_line.partition("  ")
        valid_digest = len(digest) == 64 and all(
            char in "0123456789abcdef" for char in digest
        )
        if not separator or not valid_digest or not _safe_relative_path(relative):
            issues.append(f"invalid manifest line: {path.as_posix()}:{line_number}")
            continue
        if relative in entries:
            issues.append(f"duplicate manifest path: {relative}")
            continue
        entries[relative] = digest
    return entries


def _actual_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_file() or path.is_symlink():
            files.add(relative.as_posix())
    return files


def _check_entries(
    root: Path,
    entries: dict[str, str],
    issues: list[str],
) -> None:
    for relative, expected in entries.items():
        path = root / relative
        if path.is_symlink():
            issues.append(f"frozen file must not be a symlink: {relative}")
        elif not path.is_file():
            issues.append(f"missing manifest entry file: {relative}")
        else:
            actual = _sha256(path)
            if actual != expected:
                issues.append(
                    f"hash mismatch: {relative} expected {expected}, got {actual}"
                )


def _check_inventory(
    root: Path,
    entries: dict[str, str],
    metadata_files: tuple[str, ...],
    issues: list[str],
) -> None:
    expected = set(entries).union(metadata_files)
    actual = _actual_files(root)
    for relative in sorted(expected - actual):
        issues.append(f"missing frozen inventory file: {relative}")
    for relative in sorted(actual - expected):
        issues.append(f"unexpected frozen inventory file: {relative}")


def _check_required_files(
    root: Path,
    required_files: tuple[str, ...],
    issues: list[str],
) -> None:
    for relative in required_files:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            issues.append(f"missing required file: {relative}")


def _check_inventory_manifest(
    root: Path,
    config: dict[str, object],
    entries: dict[str, str],
    issues: list[str],
) -> None:
    relative = config.get("inventory_manifest_path")
    if relative is None:
        return
    path = root / str(relative)
    expected_hash = str(config["inventory_manifest_sha256"])
    if not _check_regular_manifest(path, str(relative), issues):
        return
    if _sha256(path) != expected_hash:
        issues.append(f"hash mismatch: {relative}")
    inventory = set(path.read_text(encoding="utf-8").splitlines())
    if inventory != set(entries):
        issues.append(f"inventory manifest does not match hash manifest: {relative}")


def _check_baseline(
    workspace: Path,
    name: str,
    config: dict[str, object],
    issues: list[str],
) -> None:
    root = workspace / str(config["root"])
    if not root.is_dir():
        issues.append(f"missing frozen source root: {config['root']}")
        return
    manifest_path = root / str(config["manifest_path"])
    if not _check_regular_manifest(manifest_path, str(config["manifest_path"]), issues):
        return
    actual_manifest_hash = _sha256(manifest_path)
    if actual_manifest_hash != config["manifest_sha256"]:
        issues.append(
            f"hash mismatch: {name} manifest expected {config['manifest_sha256']}, "
            f"got {actual_manifest_hash}"
        )
    entries = _read_hash_manifest(manifest_path, issues)
    _check_entries(root, entries, issues)
    _check_inventory(root, entries, tuple(config["metadata_files"]), issues)
    _check_required_files(root, tuple(config["required_files"]), issues)
    _check_inventory_manifest(root, config, entries, issues)


def _check_source_claims(files: dict[str, bytes], issues: list[str]) -> None:
    readme = files.get("HANDOFF_README.md")
    requirements = files.get("requirements-handoff.txt")
    if readme is not None:
        text = readme.decode("utf-8", errors="replace")
        revision = str(BASELINES["quality_repair"]["source_revision"])
        if revision not in text:
            issues.append("quality_repair source revision missing from handoff README")
    if requirements is not None:
        text = requirements.decode("utf-8", errors="replace")
        version = BASELINES["quality_repair"]["claude_agent_sdk_version"]
        if f"claude-agent-sdk=={version}" not in text:
            issues.append(
                "quality_repair Claude Agent SDK pin does not match provenance"
            )


def _markdown_sections(text: str) -> tuple[dict[str, str], set[str]]:
    sections: dict[str, list[str]] = {}
    duplicates: set[str] = set()
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line.removeprefix("## ").strip()
            if current in sections:
                duplicates.add(current)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    rendered = {name: "\n".join(lines) for name, lines in sections.items()}
    return rendered, duplicates


def _metadata_value(section: str, label: str) -> str | None:
    prefix = f"- {label}: "
    values = [
        line.removeprefix(prefix).strip().strip("`")
        for line in section.splitlines()
        if line.startswith(prefix)
    ]
    return values[0] if len(values) == 1 else None


def _expected_metadata_value(name: str, key: str, config: dict[str, object]) -> str:
    override = NULL_PROVENANCE_VALUES.get((name, key))
    return override if override is not None else str(config[key])


def _check_provenance_section(
    name: str,
    config: dict[str, object],
    section: str,
    issues: list[str],
) -> None:
    for label, key in PROVENANCE_FIELDS[name]:
        expected = _expected_metadata_value(name, key, config)
        if _metadata_value(section, label) != expected:
            issues.append(f"{name} provenance mismatch: {label}")
    for key in ("windows_test_command", "linux_test_command"):
        if str(config[key]) not in section:
            issues.append(f"{name} provenance mismatch: {key}")


def _check_provenance_document(workspace: Path, issues: list[str]) -> None:
    path = workspace / "docs" / "source-provenance.md"
    if not path.is_file():
        issues.append("missing provenance document: docs/source-provenance.md")
        return
    sections, duplicates = _markdown_sections(path.read_text(encoding="utf-8"))
    for name, config in BASELINES.items():
        if name in duplicates:
            issues.append(f"duplicate provenance section: {name}")
            continue
        section = sections.get(name)
        if section is None:
            issues.append(f"missing provenance section: {name}")
            continue
        _check_provenance_section(name, config, section, issues)


def verify_workspace(workspace: Path, quality_archive: Path | None = None) -> list[str]:
    """Return sorted integrity issues for all frozen sources and metadata."""
    issues: list[str] = []
    quality_config = BASELINES["quality_repair"]
    archive = quality_archive or workspace / str(quality_config["archive_path"])
    archive_issues, quality_files = inspect_quality_archive(archive, quality_config)
    issues.extend(archive_issues)
    for name, config in BASELINES.items():
        if name == "quality_repair":
            continue
        _check_baseline(workspace, name, config, issues)
    _check_source_claims(quality_files, issues)
    _check_provenance_document(workspace, issues)
    return sorted(issues)
