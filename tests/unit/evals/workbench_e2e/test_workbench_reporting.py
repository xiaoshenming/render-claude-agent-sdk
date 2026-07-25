import json

from evals.workbench_e2e.reporting import _reported_video, build_report


def test_reported_video_accepts_recovery_baseline_inside_run_root(tmp_path):
    video = tmp_path / "slot" / "render_baseline_recovery" / "result.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")

    result = _reported_video(
        tmp_path, {"baseline_render": {"video_path": str(video)}}, "baseline_render"
    )

    assert result == video.resolve()


def test_report_separates_strict_and_warning_releases(tmp_path):
    for index, status in enumerate(("deliver", "deliver_with_warning"), start=1):
        case = tmp_path / "round-1" / f"slot-{index:03d}"
        case.mkdir(parents=True)
        (case / "job_summary.json").write_text(
            json.dumps(
                {
                    "slot_id": f"slot-{index:03d}",
                    "round_id": 1,
                    "task_id": f"task-{index}",
                    "status": status,
                    "elapsed_ms": 1,
                }
            ),
            encoding="utf-8",
        )

    report = build_report(tmp_path)

    assert report["delivery_count"] == 1
    assert report["warning_release_count"] == 1
    assert report["quality_release_count"] == 2
