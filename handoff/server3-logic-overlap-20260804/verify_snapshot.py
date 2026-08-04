from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = Path(__file__).resolve().parent
ARCHIVE = (
    ROOT / "vendor/source_archives/server3_render_logic_overlap_runtime_20260804.tar.gz"
)
EXPECTED_ARCHIVE_SHA = (
    "1ee04445f1ac88a2d894f175088c3ef9a1cce87f1eaf6a0278854d3e5da01473"
)


def digest_stream(stream: object) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):  # type: ignore[attr-defined]
        digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in (HANDOFF / "SOURCE_MANIFEST.sha256").read_text().splitlines():
        expected, path = line.split(maxsplit=1)
        entries[path] = expected
    return entries


def main() -> None:
    with ARCHIVE.open("rb") as source:
        actual_archive_sha = digest_stream(source)
    if actual_archive_sha != EXPECTED_ARCHIVE_SHA:
        raise SystemExit(f"archive SHA mismatch: {actual_archive_sha}")

    manifest = load_manifest()
    checked = 0
    with tarfile.open(ARCHIVE, "r:gz") as package:
        names = set(package.getnames())
        forbidden = [name for name in names if Path(name).name.startswith(".env")]
        if forbidden:
            raise SystemExit(f"forbidden environment files: {forbidden}")
        for path, expected in manifest.items():
            if path not in names:
                raise SystemExit(f"missing archived file: {path}")
            member = package.extractfile(path)
            if member is None:
                raise SystemExit(f"not a regular archived file: {path}")
            actual = digest_stream(member)
            if actual != expected:
                raise SystemExit(f"source SHA mismatch: {path}: {actual}")
            checked += 1

    print(f"OK archive_sha={actual_archive_sha}")
    print(f"OK core_files={checked}")
    print("OK no_dotenv_in_archive=true")


if __name__ == "__main__":
    main()
