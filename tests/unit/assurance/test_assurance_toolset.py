from pathlib import Path

import anyio

from manim_quality.assurance.models import AssuranceCase
from manim_quality.assurance.toolset import AssuranceToolset


def test_bound_tool_ignores_model_echoed_case_key(tmp_path: Path) -> None:
    case = AssuranceCase(
        key="authoritative-case",
        question="test",
        video_path=tmp_path / "video.mp4",
        log_dir=tmp_path,
    )
    toolset = AssuranceToolset(case, tmp_path)
    tool = next(
        grant for grant in toolset.grants() if grant.name == "inspect_code_review"
    )

    result = anyio.run(tool.execute, {"case_key": "model-echo-typo"})

    assert result.status == "ok"
    assert "inspect_code_review" in toolset.reports
    assert toolset.reports["inspect_code_review"].tool == "inspect_code_review"
