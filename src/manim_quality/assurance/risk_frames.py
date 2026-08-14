from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .models import AssuranceCase, ToolReport

_BLACK = re.compile(r"black_start:(?P<start>[0-9.]+).*black_end:(?P<end>[0-9.]+)")
_FREEZE = re.compile(r"freeze_start: (?P<start>[0-9.]+)|freeze_end: (?P<end>[0-9.]+)")


def inspect_risk_frames(case: AssuranceCase, output_dir: Path) -> ToolReport:
    if not case.video_path.is_file():
        return ToolReport(
            "inspect_risk_frames", "incomplete", ("missing_video",), ()
        )
    case_dir = output_dir / case.key
    case_dir.mkdir(parents=True, exist_ok=True)
    sheet = case_dir / "risk-contact-sheet.jpg"
    duration = _duration(case.video_path)
    windows = _detect_windows(case.video_path)
    sample_times = _sample_times(duration, windows)
    errors = _make_sheet(case.video_path, sheet, sample_times)
    risks = []
    if windows["black"]:
        risks.append("black_frame_window")
    if errors:
        risks.append("frame_extraction_failed")
    evidence = {
        "id": f"{case.key}:risk-frames",
        "duration_seconds": duration,
        "sample_count": len(sample_times),
        "sample_times_seconds": sample_times,
        "sampling_strategy": "black/freeze windows first, then uniform coverage",
        "windows": windows,
        "contact_sheet": str(sheet) if sheet.is_file() else None,
        "errors": errors,
    }
    artifacts = [str(sheet)] if sheet.is_file() else []
    if case.preview_video_path and case.preview_video_path.is_file():
        preview_sheet = case_dir / "preview-contact-sheet.jpg"
        preview_duration = _duration(case.preview_video_path)
        preview_windows = _detect_windows(case.preview_video_path)
        preview_times = _sample_times(preview_duration, preview_windows)
        preview_error = _make_sheet(
            case.preview_video_path, preview_sheet, preview_times
        )
        evidence["preview"] = {
            "video": str(case.preview_video_path),
            "contact_sheet": str(preview_sheet) if preview_sheet.is_file() else None,
            "sample_times_seconds": preview_times,
            "errors": preview_error,
        }
        if preview_sheet.is_file():
            artifacts.append(str(preview_sheet))
    if case.original_image_path and case.original_image_path.is_file():
        artifacts.append(str(case.original_image_path))
        evidence["original_image"] = str(case.original_image_path)
    return ToolReport(
        "inspect_risk_frames",
        "risk" if risks else ("complete" if sheet.is_file() else "incomplete"),
        tuple(risks),
        (evidence,),
        tuple(artifacts),
    )


def text_evidence(report: ToolReport) -> str:
    """Return deterministic frame telemetry without attaching image blocks."""
    return json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True)


def _duration(video: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return max(0.1, float(completed.stdout.strip()))
    except ValueError:
        return 0.1


def _make_sheet(video: Path, output: Path, times: list[float]) -> str | None:
    selections = [
        f"between(t\\,{max(0.0, value - 0.04):.3f}\\,{value + 0.04:.3f})"
        for value in times
    ]
    select = "+".join(selections) or "eq(n\\,0)"
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"select={select},scale=280:-2,tile=4x3:padding=4:margin=4",
            "-q:v",
            "3",
            "-frames:v",
            "1",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return completed.stderr[-500:] if completed.returncode else None


def _sample_times(
    duration: float,
    windows: dict[str, list[dict[str, float]]],
    limit: int = 12,
) -> list[float]:
    prioritized = []
    for window in windows["black"]:
        prioritized.extend(
            (window["start"], (window["start"] + window["end"]) / 2, window["end"])
        )
    longest_freezes = sorted(
        windows["freeze"],
        key=lambda row: row["end"] - row["start"],
        reverse=True,
    )
    prioritized.extend(
        (row["start"] + row["end"]) / 2 for row in longest_freezes[:4]
    )
    priority_limit = min(6, limit // 2)
    priority = _unique_times(prioritized, duration, priority_limit)
    uniform_count = limit - len(priority)
    uniform = (
        duration * index / max(1, uniform_count - 1)
        for index in range(uniform_count)
    )
    combined = _unique_times((*priority, *uniform), duration, limit)
    if len(combined) < limit:
        fillers = (duration * index / (limit * 2 - 1) for index in range(limit * 2))
        combined = _unique_times((*combined, *fillers), duration, limit)
    return sorted(combined)


def _unique_times(values, duration: float, limit: int) -> list[float]:
    result = []
    minimum_gap = min(0.15, duration / (limit * 2))
    for value in values:
        bounded = round(min(max(float(value), 0.0), duration), 3)
        if all(abs(bounded - existing) >= minimum_gap for existing in result):
            result.append(bounded)
        if len(result) == limit:
            break
    return sorted(result)


def _detect_windows(video: Path) -> dict[str, list[dict[str, float]]]:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(video),
            "-vf",
            "blackdetect=d=0.25:pix_th=0.02,freezedetect=n=-55dB:d=1.5",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    black = [
        {"start": float(match["start"]), "end": float(match["end"])}
        for match in _BLACK.finditer(completed.stderr)
    ]
    freeze = _freeze_windows(completed.stderr)
    return {"black": black, "freeze": freeze}


def _freeze_windows(text: str) -> list[dict[str, float]]:
    windows = []
    start = None
    for match in _FREEZE.finditer(text):
        if match["start"] is not None:
            start = float(match["start"])
        elif start is not None and match["end"] is not None:
            windows.append({"start": start, "end": float(match["end"])})
            start = None
    return windows
