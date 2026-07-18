#!/usr/bin/env python3
"""Expose containerized Manim through the Python executable contract used by V3."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_CONTAINER_ROOT = Path("/home/manimuser/manim_media")


def build_container_command(
    arguments: tuple[str, ...],
    *,
    container: str,
    host_root: Path,
) -> tuple[str, ...]:
    root = host_root.resolve()
    mapped = tuple(_map_argument(value, root) for value in arguments)
    return (
        "docker",
        "exec",
        "-u",
        "manimuser",
        "-w",
        "/home/manimuser",
        "-e",
        "PYTHONPATH=/home/manimuser/manim_media",
        container,
        "python",
        *mapped,
    )


def prepare_media_directory(
    arguments: tuple[str, ...], *, host_root: Path
) -> None:
    try:
        index = arguments.index("--media_dir") + 1
        value = arguments[index]
    except (ValueError, IndexError):
        return
    path = Path(value).resolve()
    root = host_root.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"path outside shared media root: {path}")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o777)


def prepare_python_entrypoint(
    arguments: tuple[str, ...], *, host_root: Path
) -> None:
    """Map generated probe source paths without changing the V3 package."""
    if not arguments or arguments[0] == "-m":
        return
    entrypoint = Path(arguments[0])
    root = host_root.resolve()
    resolved = entrypoint.resolve()
    if not resolved.is_relative_to(root) or resolved.suffix != ".py":
        return
    text = resolved.read_text(encoding="utf-8")
    for match in re.finditer(
        r"config\.media_dir\s*=\s*(['\"])(.+?)\1", text
    ):
        media_dir = Path(match.group(2)).resolve()
        if media_dir.is_relative_to(root):
            media_dir.mkdir(parents=True, exist_ok=True)
            media_dir.chmod(0o777)
    mapped = text.replace(str(root), str(_CONTAINER_ROOT))
    if mapped != text:
        resolved.write_text(mapped, encoding="utf-8")


def _map_argument(value: str, host_root: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        return value
    resolved = path.resolve()
    if not resolved.is_relative_to(host_root):
        raise ValueError(f"path outside shared media root: {resolved}")
    return str(_CONTAINER_ROOT / resolved.relative_to(host_root))


def main() -> int:
    container = os.environ.get("MANIM_QUALITY_CONTAINER", "manim-worker-1").strip()
    host_root = Path(
        os.environ.get(
            "MANIM_QUALITY_HOST_MEDIA_ROOT",
            "/opt/mathpi/apps/render/manim_media",
        )
    )
    try:
        prepare_media_directory(tuple(sys.argv[1:]), host_root=host_root)
        prepare_python_entrypoint(tuple(sys.argv[1:]), host_root=host_root)
        command = build_container_command(
            tuple(sys.argv[1:]),
            container=container,
            host_root=host_root,
        )
        return subprocess.run(command, check=False).returncode
    except (OSError, ValueError) as error:
        print(f"manim container adapter failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
