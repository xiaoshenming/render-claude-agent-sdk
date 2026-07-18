from __future__ import annotations

import sys
from pathlib import Path


PLATFORM_SOURCE = Path(__file__).resolve().parents[1] / "manim_quality_platform" / "src"
if str(PLATFORM_SOURCE) not in sys.path:
    sys.path.insert(0, str(PLATFORM_SOURCE))

from manim_quality.agents.guards import ToolGuard  # noqa: E402
from manim_quality.agents.profile import reviewer_profile  # noqa: E402


def test_guard_recovers_one_sdk_duplicated_workspace_prefix(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    workspace.mkdir()
    candidate = workspace / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    guard = ToolGuard(
        workspace=workspace,
        profile=reviewer_profile(model="test", prompt_version="v1"),
        readable_paths=(candidate,),
        editable_paths=(),
    )
    duplicated = workspace / str(candidate).lstrip("/")

    result = guard.authorize("Read", {"file_path": str(duplicated)})

    assert result["file_path"] == str(candidate.resolve())
