import json
from pathlib import Path

import pytest

from app.quality_platform import v3_three_state


def _render_result(folder: Path, video: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "render.json").write_text(
        json.dumps({"video_path": str(video)}), encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_persist_v3_three_state_maps_real_abc_artifacts(monkeypatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    original_video = tmp_path / "original.mp4"
    logic_video = tmp_path / "logic.mp4"
    layout_video = tmp_path / "layout.mp4"
    for path in (original_video, logic_video, layout_video):
        path.write_bytes(path.name.encode())
    logic_code = run_dir / "logic.py"
    layout_code = run_dir / "layout.py"
    logic_code.write_text("value = 2\n", encoding="utf-8")
    layout_code.write_text("value = 2\nshift = 1\n", encoding="utf-8")
    _render_result(run_dir / "render_after_logic", logic_video)
    _render_result(run_dir / "render_after_layout", layout_video)
    result_path = run_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "logic": {"status": "candidate_ready", "candidate_path": str(logic_code)},
                "layout": {
                    "status": "candidate_recheck_required",
                    "candidate_path": str(layout_code),
                    "before_blocking": 10,
                    "after_blocking": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    async def fake_persist(*, case_dir, manifest):
        captured["case_dir"] = case_dir
        captured["manifest"] = manifest
        return {"job_id": manifest.job_id}

    monkeypatch.setattr(v3_three_state, "persist_quality_case", fake_persist)
    result = await v3_three_state.persist_v3_three_state(
        job_id="job-v3",
        aspect_ratio="16:9",
        original_code="value = 1\n",
        original_video_path=str(original_video),
        result_path=result_path,
    )

    manifest = captured["manifest"]
    assert result == {"job_id": "job-v3"}
    assert manifest.pipeline == "v3_minimal"
    assert Path(manifest.baseline.video_path) == original_video
    assert Path(manifest.logic_fixed.video_path) == logic_video
    assert Path(manifest.layout_fixed.video_path) == layout_video
    assert manifest.logic_fixed.status == "repaired"
    assert manifest.layout_fixed.status == "repaired"
    assert manifest.layout_fixed.before_overlap_count == 10
    assert manifest.layout_fixed.after_overlap_count == 1


@pytest.mark.asyncio
async def test_persist_v3_three_state_reuses_previous_state_when_no_stage_render(
    monkeypatch, tmp_path: Path
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    original_video = tmp_path / "original.mp4"
    original_video.write_bytes(b"video")
    result_path = run_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "logic": {"status": "review_pass"},
                "layout": {"status": "clean", "before_blocking": 0, "after_blocking": 0},
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    async def fake_persist(*, case_dir, manifest):
        captured["manifest"] = manifest
        return {}

    monkeypatch.setattr(v3_three_state, "persist_quality_case", fake_persist)
    await v3_three_state.persist_v3_three_state(
        job_id="job-clean",
        aspect_ratio="16:9",
        original_code="value = 1\n",
        original_video_path=str(original_video),
        result_path=result_path,
    )

    manifest = captured["manifest"]
    assert manifest.baseline.video_path == manifest.logic_fixed.video_path
    assert manifest.logic_fixed.video_path == manifest.layout_fixed.video_path
    assert manifest.logic_fixed.status == "not_triggered"
    assert manifest.layout_fixed.status == "not_triggered"
