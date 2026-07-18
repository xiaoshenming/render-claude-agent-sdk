"""Filesystem writes for repair workdir assembly."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..schemas import SCHEMA_VERSION, write_json
from ..semantic_contract import GeneratedLogicContract
from .workdir_layout import _compact_layout_context_for_agent, _find_safe_area
from .workdir_normalize import COLLISION_KEYS, _find_list_field

DEFAULT_SAFE_AREA: dict[str, float] = {"x_min": -7.1, "x_max": 7.1, "y_min": -4.0, "y_max": 4.0}
PROTECTED_DEFAULT: dict[str, Any] = {
    "forbidden_patterns": ["set_speech_service", "class GlobalConfig", "def show_text", "def setup_layout"],
    "protect_string_literals": True,
    "notes": "MathTex/Tex 字符串字面量、set_color 调用、Header ABI 函数不得被修改",
}


def _write_facts(
    dest: Path,
    bundle: Any,
    layout_ctx: dict[str, Any] | None,
    logic_contract: dict[str, Any] | None,
    warnings: list[str],
    *,
    generated_logic: GeneratedLogicContract | None = None,
) -> None:
    facts_dir = dest / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    if layout_ctx is not None:
        write_json(facts_dir / "layout_context.json", layout_ctx)
        write_json(dest / "layout_context.json", _compact_layout_context_for_agent(layout_ctx))
    if logic_contract is not None:
        write_json(facts_dir / "logic_contract.json", logic_contract)
        write_json(dest / "logic_contract_context.json", logic_contract)
        write_json(dest / "logic_contract.json", logic_contract)
    if bundle.source_region is not None:
        _copy_optional_file(bundle.source_region, facts_dir / "source_region.md", warnings, "source_region")
        _copy_optional_file(bundle.source_region, dest / "source_region.md", warnings, "source_region")
    elif generated_logic is not None:
        (facts_dir / "source_region.md").write_text(generated_logic.source_region, encoding="utf-8")
        (dest / "source_region.md").write_text(generated_logic.source_region, encoding="utf-8")
        payload = {"schema_version": SCHEMA_VERSION, "findings": generated_logic.findings}
        write_json(facts_dir / "review_findings.json", payload)
        write_json(dest / "review_findings.json", payload)


def _copy_optional_file(src: Path | None, dst: Path, warnings: list[str], label: str) -> None:
    if src is None:
        return
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        warnings.append(f"{label}_copy_failed:{src}:{exc}")


def _extract_safe_area(dest: Path, layout_ctx: dict[str, Any] | None) -> None:
    safe_area = _find_safe_area(layout_ctx) if layout_ctx else None
    write_json(dest / "facts" / "safe_area.json", {"schema_version": SCHEMA_VERSION, **(safe_area or DEFAULT_SAFE_AREA)})


def _extract_collisions(dest: Path, layout_ctx: dict[str, Any] | None) -> None:
    _write_json_value(dest / "facts" / "collisions.json", _find_list_field(layout_ctx, COLLISION_KEYS))


def _write_json_value(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_protected(dest: Path, *, protect_string_literals: bool | None = None) -> None:
    payload = {"schema_version": SCHEMA_VERSION, **PROTECTED_DEFAULT}
    if protect_string_literals is not None:
        payload["protect_string_literals"] = protect_string_literals
    write_json(dest / "facts" / "protected.json", payload)


def _copy_frames(frames: list[Path], dest: Path, warnings: list[str]) -> None:
    if not frames:
        return
    frames_dir = dest / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        try:
            shutil.copy2(frame, frames_dir / frame.name)
        except OSError as exc:
            warnings.append(f"frame_copy_failed:{frame}:{exc}")
