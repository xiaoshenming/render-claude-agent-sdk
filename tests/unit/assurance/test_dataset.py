import json
from pathlib import Path

from manim_quality.assurance.dataset import (
    load_annotated_cases,
    load_curated_cases,
    load_successful_cases,
)


def test_dataset_binds_annotations_gallery_and_logs(tmp_path) -> None:
    forensic = tmp_path / "forensic"
    gallery = tmp_path / "gallery"
    logs = tmp_path / "logs"
    forensic.mkdir()
    gallery.mkdir()
    (logs / "CASE-001").mkdir(parents=True)
    (forensic / "human_annotations.json").write_text(
        json.dumps({"overlap": ["CASE-001"]}), encoding="utf-8"
    )
    (forensic / "case_explanations_41.json").write_text(
        json.dumps({"cases": {"CASE-001": {"verdict": "机器假通过"}}}),
        encoding="utf-8",
    )
    (gallery / "manifest.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "external_key": "CASE-001",
                        "question": "test",
                        "stages": {"before": {"path": "media/a.mp4"}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_annotated_cases(forensic, gallery, logs)

    assert len(cases) == 1
    assert cases[0].human_tags == ("overlap",)
    assert cases[0].video_path == gallery / "media/a.mp4"


def test_load_successful_cases_uses_only_complete_final_videos(tmp_path: Path) -> None:
    gallery = tmp_path / "gallery"
    logs = tmp_path / "logs"
    gallery.mkdir()
    (gallery / "manifest.json").write_text(
        json.dumps(
            {
                "items": [
                    _gallery_item("OK-1", "succeeded", "media/final.mp4"),
                    _gallery_item("BAD-1", "failed", "media/bad.mp4"),
                    _gallery_item("MISS-1", "succeeded", None),
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_successful_cases(gallery, logs)

    assert [case.key for case in cases] == ["OK-1"]
    assert cases[0].video_path == gallery / "media/final.mp4"


def _gallery_item(key: str, status: str, path: str | None) -> dict:
    stages = {"overlap": {"path": path}} if path else {}
    return {
        "external_key": key,
        "item_status": status,
        "question": "question",
        "stages": stages,
    }


def test_curated_case_binds_optional_comparison_media(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "key": "CASE-1",
                    "video": {"sha256": "abc"},
                    "original_image_path": "original.png",
                    "preview_video_path": "preview.mp4",
                    "subtitle_path": "final.srt",
                    "tts_mode": "silent",
                }
            ]
        ),
        encoding="utf-8",
    )

    case = load_curated_cases(manifest, tmp_path / "logs")[0]

    assert case.original_image_path == tmp_path / "original.png"
    assert case.preview_video_path == tmp_path / "preview.mp4"
    assert case.subtitle_path == tmp_path / "final.srt"
    assert case.tts_mode == "silent"
