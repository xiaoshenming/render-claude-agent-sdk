from __future__ import annotations

import json
from pathlib import Path

from .models import AssuranceInput, AssuranceLabel, LabeledAssuranceCase


def load_annotated_cases(
    forensic_dir: Path,
    gallery_dir: Path,
    logs_dir: Path,
) -> tuple[LabeledAssuranceCase, ...]:
    annotations = _object(forensic_dir / "human_annotations.json")
    explanations = _object(forensic_dir / "case_explanations_41.json").get(
        "cases", {}
    )
    gallery = _object(gallery_dir / "manifest.json").get("items", [])
    by_key = {
        row.get("external_key"): row
        for row in gallery
        if isinstance(row, dict) and isinstance(row.get("external_key"), str)
    }
    tag_map: dict[str, list[str]] = {}
    for tag, keys in annotations.items():
        if not isinstance(keys, list):
            continue
        for key in keys:
            if isinstance(key, str):
                tag_map.setdefault(key, []).append(tag)
    cases = []
    if not isinstance(explanations, dict):
        return ()
    for key, explanation in explanations.items():
        item = by_key.get(key, {})
        stage = _selected_stage(item.get("stages"))
        relative = stage.get("path") if isinstance(stage, dict) else None
        video = gallery_dir / str(relative or "missing.mp4")
        verdict = explanation.get("verdict") if isinstance(explanation, dict) else ""
        cases.append(
            LabeledAssuranceCase(
                assurance_input=AssuranceInput(
                    key=key,
                    question=str(item.get("question") or ""),
                    video_path=video,
                    log_dir=logs_dir / key,
                ),
                label=_label_from_verdict(str(verdict or ""), tag_map.get(key, ())),
                human_tags=tuple(sorted(tag_map.get(key, ()))),
                expected_verdict=str(verdict or ""),
            )
        )
    return tuple(cases)


def load_successful_cases(
    gallery_dir: Path,
    logs_dir: Path,
) -> tuple[LabeledAssuranceCase, ...]:
    gallery = _object(gallery_dir / "manifest.json").get("items", [])
    if not isinstance(gallery, list):
        return ()
    cases = []
    for item in gallery:
        if not isinstance(item, dict) or item.get("item_status") != "succeeded":
            continue
        key = item.get("external_key")
        stage = _selected_stage(item.get("stages"))
        relative = stage.get("path") if isinstance(stage, dict) else None
        if not isinstance(key, str) or not relative:
            continue
        cases.append(
            LabeledAssuranceCase(
                assurance_input=AssuranceInput(
                    key=key,
                    question=str(item.get("question") or ""),
                    video_path=gallery_dir / str(relative),
                    log_dir=logs_dir / key,
                ),
                label=AssuranceLabel.UNLABELED,
            )
        )
    return tuple(cases)


def load_curated_cases(
    manifest_path: Path,
    logs_dir: Path,
) -> tuple[LabeledAssuranceCase, ...]:
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return ()
    root = manifest_path.parent
    return tuple(
        LabeledAssuranceCase(
            assurance_input=AssuranceInput(
                key=str(row["key"]),
                question=str(row.get("question") or ""),
                video_path=root / "videos" / f"{row['key']}.mp4",
                source_path=root / "sources" / str(row["key"]) / "main.py",
                subtitle_path=_optional_path(root, row.get("subtitle_path")),
                original_image_path=_optional_path(
                    root, row.get("original_image_path")
                ),
                preview_video_path=_optional_path(root, row.get("preview_video_path")),
                log_dir=logs_dir / str(row["key"]),
                delivery_revision_id=(
                    str(row["final_revision_id"])
                    if row.get("final_revision_id")
                    else None
                ),
                expected_video_sha256=str(row["video"]["sha256"]),
                expected_source_sha256=_optional_sha(row, "source"),
                render_manifest_path=_optional_path(
                    root, row.get("render_manifest_path")
                ),
                expected_render_manifest_sha256=_optional_sha(row, "render_manifest"),
                tts_mode=str(row.get("tts_mode") or "required"),
            ),
            label=AssuranceLabel(str(row.get("label") or "UNLABELED").upper()),
            human_tags=tuple(filter(None, (str(row.get("group") or ""),))),
        )
        for row in rows
    )


def _selected_stage(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    for name in ("overlap", "logic", "before"):
        stage = value.get(name)
        if isinstance(stage, dict) and stage.get("path"):
            return stage
    return {}


def _object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _optional_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _optional_sha(row: dict, name: str) -> str | None:
    value = row.get(name)
    if isinstance(value, dict) and value.get("sha256"):
        return str(value["sha256"])
    return None


def _label_from_verdict(verdict: str, tags: list[str]) -> AssuranceLabel:
    if verdict.lower() in {"pass", "通过", "正确"} or "control" in tags:
        return AssuranceLabel.GOOD
    return AssuranceLabel.BAD if verdict or tags else AssuranceLabel.UNLABELED
