from __future__ import annotations

import io
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).parents[2]
ARCHIVE = (
    ROOT
    / "vendor"
    / "source_archives"
    / "quality_repair_source_handoff_20260711_platform1.tar.gz"
)
MATERIALIZER = ROOT / "scripts" / "materialize_quality_repair.py"


def _run_materializer(archive: Path, target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--archive",
            str(archive),
            "--target",
            str(target),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_overlap_vendor_is_archive_only_in_active_tree() -> None:
    assert ARCHIVE.is_file()
    assert not (ROOT / "packages" / "quality_repair").exists()


def test_materializer_extracts_verified_handoff(tmp_path: Path) -> None:
    target = tmp_path / "quality_repair"

    result = _run_materializer(ARCHIVE, target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "HANDOFF_README.md").is_file()
    assert (target / "libs" / "quality_repair" / "api.py").is_file()
    assert not (target / "quality_repair_source_handoff_20260711_platform1").exists()


def test_materialized_root_is_traversable_by_service_accounts(tmp_path: Path) -> None:
    target = tmp_path / "quality_repair"

    result = _run_materializer(ARCHIVE, target)

    assert result.returncode == 0, result.stdout + result.stderr
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_materializer_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        payload = b"escape"
        member = tarfile.TarInfo(
            "quality_repair_source_handoff_20260711_platform1/../escape.txt"
        )
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))

    target = tmp_path / "quality_repair"
    result = _run_materializer(archive, target)

    assert result.returncode != 0
    assert "unsafe archive member" in (result.stdout + result.stderr)
    assert not (tmp_path / "escape.txt").exists()


def test_materializer_refuses_nonempty_target(tmp_path: Path) -> None:
    target = tmp_path / "quality_repair"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")

    result = _run_materializer(ARCHIVE, target)

    assert result.returncode != 0
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"
