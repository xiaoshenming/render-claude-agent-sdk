from __future__ import annotations

import ast
import difflib
import re
import subprocess
from pathlib import Path

from .models import AssuranceCase, ToolReport


def inspect_tts(case: AssuranceCase) -> ToolReport:
    mode = case.tts_mode.strip().lower()
    if mode in {"silent", "disabled", "off"}:
        return _report(
            "complete",
            (),
            {
                "id": f"{case.key}:tts-audio",
                "tts_mode": mode,
                "audio_required": False,
                "inspection": "not_applicable",
                "reason": "tts_disabled_by_sample_contract",
                "subtitle": str(case.subtitle_path) if case.subtitle_path else None,
            },
        )
    audio = _audio_levels(case.video_path)
    risks = []
    if not audio.get("has_audio"):
        risks.append("missing_audio_stream")
    elif _effectively_silent(audio.get("max_volume")):
        risks.append("silent_audio_stream")
    evidence = {
        "id": f"{case.key}:tts-audio",
        "tts_mode": mode,
        "audio_required": True,
        **audio,
        "subtitle": str(case.subtitle_path) if case.subtitle_path else None,
    }
    if risks:
        return _report("risk", tuple(risks), evidence)
    if case.subtitle_path is None or not case.subtitle_path.is_file():
        return _report("incomplete", ("subtitle_not_supplied",), evidence)
    comparison = _narration_comparison(case.source_path, case.subtitle_path)
    evidence["narration_comparison"] = comparison
    if comparison.get("verified") and comparison.get("similarity", 1.0) < 0.75:
        return _report("risk", ("subtitle_narration_mismatch",), evidence)
    return _report("complete", (), evidence)


def _narration_comparison(
    source_path: Path | None,
    subtitle_path: Path,
) -> dict[str, object]:
    source_texts = _voiceover_texts(source_path)
    subtitle_text = _subtitle_text(subtitle_path)
    if not source_texts or not subtitle_text:
        return {
            "verified": False,
            "reason": "source_voiceover_or_subtitle_text_missing",
            "source_blocks": len(source_texts),
        }
    source_text = _normalize_narration("".join(source_texts))
    subtitle_text = _normalize_narration(subtitle_text)
    similarity = difflib.SequenceMatcher(
        None, source_text, subtitle_text, autojunk=False
    ).ratio()
    return {
        "verified": True,
        "source_blocks": len(source_texts),
        "source_characters": len(source_text),
        "subtitle_characters": len(subtitle_text),
        "similarity": round(similarity, 4),
    }


def _voiceover_texts(source_path: Path | None) -> tuple[str, ...]:
    if source_path is None or not source_path.is_file():
        return ()
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return ()
    values = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "voiceover":
            continue
        for keyword in node.keywords:
            if keyword.arg == "text" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, str):
                    values.append(keyword.value.value)
    return tuple(values)


def _subtitle_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit() or "-->" in stripped:
            continue
        lines.append(re.sub(r"<[^>]+>", "", stripped))
    return "".join(lines)


def _normalize_narration(value: str) -> str:
    return "".join(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", value)).lower()


def _audio_levels(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    text = completed.stderr
    maximum = re.search(r"max_volume:\s*(?P<value>-?inf|-?[0-9.]+) dB", text)
    mean = re.search(r"mean_volume:\s*(?P<value>-?inf|-?[0-9.]+) dB", text)
    return {
        "has_audio": "Audio:" in text,
        "max_volume": maximum.group("value") if maximum else None,
        "mean_volume": mean.group("value") if mean else None,
        "ffmpeg_returncode": completed.returncode,
    }


def _effectively_silent(value: object) -> bool:
    if value == "-inf":
        return True
    try:
        return float(str(value)) <= -60.0
    except (TypeError, ValueError):
        return False


def _report(status: str, risks: tuple[str, ...], evidence: dict) -> ToolReport:
    return ToolReport("inspect_tts", status, risks, (evidence,))
