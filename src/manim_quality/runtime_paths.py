"""Resolve release-owned assets from source and installed wheel layouts."""

from pathlib import Path


def release_asset(module_path: Path | str, relative: Path | str) -> Path:
    requested = Path(relative)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("release asset path must be relative and contained")
    for parent in Path(module_path).resolve(strict=True).parents:
        candidate = parent / requested
        if candidate.is_file():
            return candidate.resolve(strict=True)
    raise FileNotFoundError(f"release asset missing: {requested}")
