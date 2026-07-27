from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

from manim_quality.agents.managed_tools import ManagedToolContent

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
    errors = _make_sheet(case.video_path, sheet, duration)
    windows = _detect_windows(case.video_path)
    risks = []
    if windows["black"]:
        risks.append("black_frame_window")
    if errors:
        risks.append("frame_extraction_failed")
    evidence = {
        "id": f"{case.key}:risk-frames",
        "duration_seconds": duration,
        "sample_count": 12,
        "windows": windows,
        "contact_sheet": str(sheet) if sheet.is_file() else None,
        "errors": errors,
    }
    return ToolReport(
        "inspect_risk_frames",
        "risk" if risks else ("complete" if sheet.is_file() else "incomplete"),
        tuple(risks),
        (evidence,),
        (str(sheet),) if sheet.is_file() else (),
    )


def multimodal_content(report: ToolReport) -> ManagedToolContent:
    audit = json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True)
    blocks: list[dict[str, object]] = [{"type": "text", "text": audit}]
    for path in report.artifacts:
        image = Path(path)
        if image.is_file():
            blocks.append(
                {
                    "type": "image",
                    "data": base64.b64encode(image.read_bytes()).decode("ascii"),
                    "mimeType": "image/jpeg",
                }
            )
    return ManagedToolContent(audit_text=audit, blocks=tuple(blocks))


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


def _make_sheet(video: Path, output: Path, duration: float) -> str | None:
    fps = 12 / duration
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            f"fps={fps:.8f},scale=280:-2,tile=4x3:padding=4:margin=4",
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
