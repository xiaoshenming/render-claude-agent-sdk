"""Temporary workspace adjustments for Claude SDK runs."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

WORKSPACE_ROOT = Path("/workspace")


@contextmanager
def _hide_checker_config_during_sdk(workdir: Path):
    config = workdir / "tool_config.json"
    hidden = workdir / ".tool_config.hidden_for_sdk"
    moved = False
    try:
        if config.exists() and not hidden.exists():
            config.rename(hidden)
            moved = True
        yield
    finally:
        if moved and hidden.exists():
            hidden.rename(config)


@contextmanager
def _mirror_workspace_files_during_sdk(workdir: Path):
    workspace = WORKSPACE_ROOT
    created_workspace = False
    created: list[Path] = []
    try:
        if not workspace.exists():
            try:
                workspace.mkdir()
                created_workspace = True
            except OSError:
                yield
                return
        if workspace.is_dir():
            for name in ("layout_issue_digest.json", "candidate.py"):
                source = workdir / name
                target = workspace / name
                if source.exists() and not target.exists():
                    target.symlink_to(source)
                    created.append(target)
        yield
    finally:
        for target in reversed(created):
            try:
                if target.is_symlink():
                    target.unlink()
            except OSError:
                pass
        if created_workspace:
            try:
                workspace.rmdir()
            except OSError:
                pass
