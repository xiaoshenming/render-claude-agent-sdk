from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.vendor_verification import BASELINES

ROOT = Path(__file__).parents[2]
VERIFY_SCRIPT = ROOT / "scripts" / "verify_vendor_sources.py"
PROVENANCE_DOC = ROOT / "docs" / "source-provenance.md"
QUALITY_ARCHIVE_REL = Path(
    "vendor/source_archives/quality_repair_source_handoff_20260711_platform1.tar.gz"
)

DOCUMENT_FIELD_CASES = (
    (
        "quality_repair",
        "Original archive SHA-256",
        "source_archive_sha256",
    ),
    ("quality_repair", "Reported source revision", "source_revision"),
    ("quality_repair", "File manifest SHA-256", "manifest_sha256"),
    (
        "quality_repair",
        "Inventory manifest SHA-256",
        "inventory_manifest_sha256",
    ),
    ("logic_self_audit_baseline", "Content identity", "content_identity"),
    ("logic_engine_mvp_baseline", "Content identity", "content_identity"),
)

MANIFEST_LINK_CASES = (
    ("vendor/logic_self_audit_baseline", "SOURCE_MANIFEST.sha256"),
    ("vendor/logic_engine_mvp_baseline", "SOURCE_MANIFEST.sha256"),
)

LOGIC_NULL_FIELD_CASES = (
    (
        "logic_self_audit_baseline",
        "Source revision",
        "none.",
    ),
    (
        "logic_self_audit_baseline",
        "Original archive SHA-256",
        "not applicable; this source was not an archive.",
    ),
    ("logic_engine_mvp_baseline", "Source revision", "none."),
    (
        "logic_engine_mvp_baseline",
        "Original archive SHA-256",
        "not applicable; this source was not an archive.",
    ),
)


def _load_baselines() -> dict[str, dict[str, object]]:
    assert VERIFY_SCRIPT.is_file(), "offline verifier has not been implemented"
    return BASELINES


def _run_verifier(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--root", str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _copy_frozen_roots(destination: Path) -> None:
    archive = ROOT / QUALITY_ARCHIVE_REL
    assert archive.is_file(), f"missing frozen source archive: {QUALITY_ARCHIVE_REL}"
    archive_target = destination / QUALITY_ARCHIVE_REL
    archive_target.parent.mkdir(parents=True)
    shutil.copy2(archive, archive_target)
    for relative_text in (
        "vendor/logic_self_audit_baseline",
        "vendor/logic_engine_mvp_baseline",
    ):
        relative = Path(relative_text)
        source = ROOT / relative
        assert source.is_dir(), f"missing frozen source root: {relative}"
        shutil.copytree(source, destination / relative)
    doc_target = destination / "docs" / "source-provenance.md"
    doc_target.parent.mkdir(parents=True)
    shutil.copy2(PROVENANCE_DOC, doc_target)
def test_offline_verifier_rejects_archive_link_escape(tmp_path: Path) -> None:
    _copy_frozen_roots(tmp_path)
    archive = tmp_path / QUALITY_ARCHIVE_REL
    outside = tmp_path / "outside.tar.gz"
    shutil.copy2(archive, outside)
    archive.unlink()
    try:
        archive.symlink_to(outside)
    except NotImplementedError as error:
        if sys.platform != "win32":
            raise
        pytest.skip(f"file symlink unavailable on Windows: {error}")
    except OSError as error:
        if sys.platform != "win32" or getattr(error, "winerror", None) != 1314:
            raise
        pytest.skip(f"file symlink unavailable on this platform: {error}")

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert (
        "quality_repair archive must not be a symlink or reparse point" in result.stdout
    )

def test_offline_verifier_rejects_false_logic_source_claim(
    tmp_path: Path,
    baseline: str,
    label: str,
    expected: str,
) -> None:
    _copy_frozen_roots(tmp_path)
    document = tmp_path / "docs" / "source-provenance.md"
    expected_line = f"- {label}: {expected}"
    text = document.read_text(encoding="utf-8")
    section_start = text.index(f"## {baseline}")
    section_end = text.find("\n## ", section_start + 3)
    section_end = len(text) if section_end < 0 else section_end
    section = text[section_start:section_end]
    assert section.count(expected_line) == 1
    document.write_text(
        text[:section_start]
        + section.replace(expected_line, f"- {label}: fake-source-claim")
        + text[section_end:],
        encoding="utf-8",
    )

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert f"{baseline} provenance mismatch: {label}" in result.stdout

def test_offline_verifier_rejects_duplicate_baseline_section(tmp_path: Path) -> None:
    _copy_frozen_roots(tmp_path)
    document = tmp_path / "docs" / "source-provenance.md"
    text = document.read_text(encoding="utf-8")
    heading = "## quality_repair"
    section_start = text.index(heading)
    section_end = text.index("\n## ", section_start + len(heading))
    duplicate = text[section_start:section_end]
    document.write_text(f"{text}\n{duplicate}\n", encoding="utf-8")

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert "duplicate provenance section: quality_repair" in result.stdout
