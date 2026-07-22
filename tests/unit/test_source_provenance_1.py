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
def test_provenance_records_verifiable_source_metadata() -> None:
    baselines = _load_baselines()

    quality = baselines["quality_repair"]
    assert quality["source_type"] == "tar.gz archive"
    assert quality["archive_path"] == QUALITY_ARCHIVE_REL.as_posix()
    assert quality["source_archive_sha256"] == (
        "90d0a55d14d54acee640645c0fd48ad37faa7e7be6c4a8585c4e73ce6865579c"
    )
    assert quality["source_revision"] == "ae371aecd9cd258344c94ecdfa6a6cdd36417f5c"
    assert quality["compatibility_revision"] == "quality-platform.1"
    assert quality["claude_agent_sdk_version"] == "0.2.115"
    assert quality["manifest_sha256"] == (
        "18083bc719d18c22fd5fee461db4d29f9e7d487531fba20a4e57fad2355d1d93"
    )

    logic = baselines["logic_self_audit_baseline"]
    assert logic["source_type"] == "untracked working-tree snapshot"
    assert logic["source_archive_sha256"] is None
    assert logic["source_revision"] is None
    assert logic["content_identity"] == (
        "sha256:e0f123e603231a2e4a8a533a81b4befeec4c4417b9755b9b244a14d453513412"
    )
    assert logic["claude_agent_sdk_version"] == "0.2.110"
    assert logic["manifest_sha256"] == (
        "e0f123e603231a2e4a8a533a81b4befeec4c4417b9755b9b244a14d453513412"
    )
    assert "app/workers/validation/code_validator.py" in logic["required_files"]

    engine = baselines["logic_engine_mvp_baseline"]
    assert engine["source_type"] == "untracked working-tree snapshot"
    assert engine["source_archive_sha256"] is None
    assert engine["source_revision"] is None
    assert (
        "tools/logic_engine_mvp/logic_engine_mvp/logic_facts.py"
        in engine["required_files"]
    )
    assert (
        "tools/logic_engine_mvp/logic_engine_mvp/sdk_agent_runner.py"
        in engine["required_files"]
    )

    for baseline in baselines.values():
        assert baseline["windows_test_command"]
        assert "python3.11" in str(baseline["linux_test_command"])

def test_provenance_document_covers_platform_authority_and_frozen_exceptions() -> None:
    assert PROVENANCE_DOC.is_file(), "source provenance document is missing"
    text = PROVENANCE_DOC.read_text(encoding="utf-8")

    required = (
        "Windows local verification",
        "Linux / Python 3.11 authority",
        "Known platform differences",
        "untracked working-tree snapshot",
        "No Git revision is claimed",
        "Frozen vendor exception",
    )
    assert all(marker in text for marker in required)

def test_offline_verifier_accepts_frozen_sources() -> None:
    result = _run_verifier(ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Vendor source verification: PASS" in result.stdout

def test_offline_verifier_rejects_hash_tampering(tmp_path: Path) -> None:
    _copy_frozen_roots(tmp_path)
    target = (
        tmp_path
        / "vendor"
        / "logic_self_audit_baseline"
        / "app"
        / "workers"
        / "post_render_logic"
        / "schemas.py"
    )
    target.write_text(
        target.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8"
    )

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert "hash mismatch" in result.stdout

def test_offline_verifier_rejects_missing_quality_archive(tmp_path: Path) -> None:
    _copy_frozen_roots(tmp_path)
    target = tmp_path / QUALITY_ARCHIVE_REL
    target.unlink()

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert "missing source archive" in result.stdout

def test_offline_verifier_rejects_quality_archive_tampering(tmp_path: Path) -> None:
    _copy_frozen_roots(tmp_path)
    target = tmp_path / QUALITY_ARCHIVE_REL
    target.write_bytes(target.read_bytes() + b"tampered")

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert "hash mismatch: quality_repair source archive" in result.stdout

def test_offline_verifier_rejects_provenance_value_in_wrong_section(
    tmp_path: Path,
    baseline: str,
    label: str,
    config_key: str,
) -> None:
    _copy_frozen_roots(tmp_path)
    document = tmp_path / "docs" / "source-provenance.md"
    expected = str(BASELINES[baseline][config_key])
    expected_line = f"- {label}: `{expected}`"
    text = document.read_text(encoding="utf-8")
    assert text.count(expected_line) == 1
    text = text.replace(expected_line, f"- {label}: `wrong-{expected}`")
    document.write_text(
        f"{text}\n## Misplaced value\n\n`{expected}`\n",
        encoding="utf-8",
    )

    result = _run_verifier(tmp_path)

    assert result.returncode != 0
    assert f"{baseline} provenance mismatch: {label}" in result.stdout

def test_offline_verifier_rejects_manifest_link_escape(
    tmp_path: Path,
    root: str,
    manifest_name: str,
) -> None:
    _copy_frozen_roots(tmp_path)
    manifest = tmp_path / root / manifest_name
    outside = tmp_path / "outside" / manifest_name
    outside.parent.mkdir(exist_ok=True)
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    try:
        manifest.symlink_to(outside)
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
    assert "symlink or reparse point" in result.stdout
