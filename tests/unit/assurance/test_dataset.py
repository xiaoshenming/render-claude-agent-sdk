import json

from manim_quality.assurance.dataset import load_annotated_cases


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
