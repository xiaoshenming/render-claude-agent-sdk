"""SDK-only editable view for large Manim candidate.py files."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import write_json

CORE_CANDIDATE = "core_candidate.py"
PRELUDE = "candidate_prelude.txt"
CORE_MAP = "candidate_core_map.json"
CORE_MAP_SCHEMA_VERSION = "quality_repair.core_candidate_view.v1"
COMPOSE_STRATEGY = "prelude_plus_core_to_candidate_py"


@dataclass(frozen=True)
class CoreCandidateViewResult:
    enabled: bool
    fallback: bool = False
    reason: str | None = None
    scene_class: str | None = None
    core_start_line: int | None = None
    core_end_line: int | None = None
    scene_end_line: int | None = None
    candidate_sha256: str | None = None
    prelude_sha256: str | None = None
    core_sha256: str | None = None
    candidate_path: Path | None = None
    prelude_path: Path | None = None
    core_path: Path | None = None
    map_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CORE_MAP_SCHEMA_VERSION,
            "enabled": self.enabled,
            "fallback": self.fallback,
            "reason": self.reason,
            "candidate_path": _path_name(self.candidate_path, "candidate.py"),
            "prelude_path": _path_name(self.prelude_path, PRELUDE),
            "core_path": _path_name(self.core_path, CORE_CANDIDATE),
            "map_path": _path_name(self.map_path, CORE_MAP),
            "scene_class": self.scene_class,
            "core_start_line": self.core_start_line,
            "core_end_line": self.core_end_line,
            "scene_end_line": self.scene_end_line,
            "compose_strategy": COMPOSE_STRATEGY,
            "candidate_sha256": self.candidate_sha256,
            "prelude_sha256": self.prelude_sha256,
            "core_sha256": self.core_sha256,
        }


@dataclass(frozen=True)
class CoreCandidateComposeResult:
    ok: bool
    fallback: bool
    reason: str | None
    target_path: Path
    bytes_written: int = 0
    scene_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fallback": self.fallback,
            "reason": self.reason,
            "target_path": str(self.target_path),
            "bytes_written": self.bytes_written,
            "scene_class": self.scene_class,
        }


def build_core_candidate_view(workdir: Path) -> CoreCandidateViewResult:
    return prepare_core_candidate_view(workdir)


def prepare_core_candidate_view(workdir: Path) -> CoreCandidateViewResult:
    """Create a compact editable Scene view. Failures are recorded, not raised."""
    candidate = workdir / "candidate.py"
    try:
        source = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        return _write_disabled(workdir, f"candidate_read_error:{exc}")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return _write_disabled(workdir, f"parse_error:{exc.lineno}:{exc.msg}")

    scene = _first_scene_with_construct(tree)
    if scene is None:
        return _write_disabled(workdir, "no_scene_with_construct")

    lines = source.splitlines(keepends=True)
    start = _class_start_line(scene)
    scene_end = getattr(scene, "end_lineno", None)
    end = len(lines)
    if start < 1 or end < start:
        return _write_disabled(workdir, "invalid_scene_line_bounds")

    prelude = "".join(lines[: start - 1])
    core = "".join(lines[start - 1 :])
    if not core:
        return _write_disabled(workdir, "empty_core_candidate")

    (workdir / PRELUDE).write_text(prelude, encoding="utf-8")
    (workdir / CORE_CANDIDATE).write_text(core, encoding="utf-8")
    result = CoreCandidateViewResult(
        enabled=True,
        fallback=False,
        scene_class=scene.name,
        core_start_line=start,
        core_end_line=end,
        scene_end_line=scene_end,
        candidate_sha256=_sha256(source),
        prelude_sha256=_sha256(prelude),
        core_sha256=_sha256(core),
        candidate_path=candidate,
        prelude_path=workdir / PRELUDE,
        core_path=workdir / CORE_CANDIDATE,
        map_path=workdir / CORE_MAP,
    )
    write_json(workdir / CORE_MAP, result.to_dict())
    return result


def compose_core_candidate(workdir: Path) -> CoreCandidateViewResult:
    """Compose full candidate.py from the compact view when it is enabled."""
    composed = compose_candidate_from_core(workdir)
    if not composed.ok:
        return _disabled_result(workdir, composed.reason or "compose_failed")
    return read_core_candidate_view(workdir)


def compose_candidate_from_core(workdir: Path, target_path: Path | None = None) -> CoreCandidateComposeResult:
    target = target_path or workdir / "candidate.py"
    current = read_core_candidate_view(workdir)
    if not current.enabled:
        return CoreCandidateComposeResult(
            ok=False,
            fallback=True,
            reason=current.reason,
            target_path=target,
            scene_class=current.scene_class,
        )

    prelude_path = current.prelude_path or workdir / PRELUDE
    core_path = current.core_path or workdir / CORE_CANDIDATE
    try:
        prelude = prelude_path.read_text(encoding="utf-8")
        core = core_path.read_text(encoding="utf-8")
    except OSError:
        return CoreCandidateComposeResult(
            ok=False,
            fallback=True,
            reason="view_files_missing",
            target_path=target,
            scene_class=current.scene_class,
        )

    combined = prelude + core
    try:
        ast.parse(combined)
    except SyntaxError as exc:
        return CoreCandidateComposeResult(
            ok=False,
            fallback=True,
            reason=f"compose_parse_error:{exc.lineno}:{exc.msg}",
            target_path=target,
            scene_class=current.scene_class,
        )
    try:
        tmp_target = target.with_name(f"{target.name}.core-compose.tmp")
        tmp_target.write_text(combined, encoding="utf-8")
        tmp_target.replace(target)
    except OSError as exc:
        return CoreCandidateComposeResult(
            ok=False,
            fallback=True,
            reason=f"candidate_write_error:{exc}",
            target_path=target,
            scene_class=current.scene_class,
        )

    result = CoreCandidateViewResult(
        enabled=True,
        fallback=False,
        scene_class=current.scene_class,
        core_start_line=current.core_start_line,
        core_end_line=len(combined.splitlines()),
        scene_end_line=current.scene_end_line,
        candidate_sha256=_sha256(combined),
        prelude_sha256=_sha256(prelude),
        core_sha256=_sha256(core),
        candidate_path=target,
        prelude_path=prelude_path,
        core_path=core_path,
        map_path=workdir / CORE_MAP,
    )
    write_json(workdir / CORE_MAP, result.to_dict())
    return CoreCandidateComposeResult(
        ok=True,
        fallback=False,
        reason=None,
        target_path=target,
        bytes_written=len(combined.encode("utf-8")),
        scene_class=current.scene_class,
    )


def read_core_candidate_view(workdir: Path) -> CoreCandidateViewResult:
    return _read_map(workdir)


def core_candidate_enabled(workdir: Path) -> bool:
    status = read_core_candidate_view(workdir)
    return bool(status.enabled and (workdir / CORE_CANDIDATE).exists() and (workdir / PRELUDE).exists())


def editable_candidate_path(workdir: Path) -> str:
    return CORE_CANDIDATE if core_candidate_enabled(workdir) else "candidate.py"


def _first_scene_with_construct(tree: ast.AST) -> ast.ClassDef | None:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef) and any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "construct"
            for item in node.body
        ):
            return node
    return None


def _read_map(workdir: Path) -> CoreCandidateViewResult:
    path = workdir / CORE_MAP
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _disabled_result(workdir, f"map_read_error:{exc}")
    if not isinstance(data, dict):
        return _disabled_result(workdir, "map_invalid")

    candidate_path = _resolve_workdir_path(workdir, data.get("candidate_path"), "candidate.py")
    prelude_path = _resolve_workdir_path(workdir, data.get("prelude_path"), PRELUDE)
    core_path = _resolve_workdir_path(workdir, data.get("core_path"), CORE_CANDIDATE)
    enabled = bool(data.get("enabled"))
    result = CoreCandidateViewResult(
        enabled=bool(data.get("enabled")),
        fallback=bool(data.get("fallback", not enabled)),
        reason=data.get("reason") if data.get("reason") is None or isinstance(data.get("reason"), str) else str(data.get("reason")),
        scene_class=data.get("scene_class") if data.get("scene_class") is None or isinstance(data.get("scene_class"), str) else str(data.get("scene_class")),
        core_start_line=_optional_int(data.get("core_start_line")),
        core_end_line=_optional_int(data.get("core_end_line")),
        scene_end_line=_optional_int(data.get("scene_end_line")),
        candidate_sha256=_optional_str(data.get("candidate_sha256")),
        prelude_sha256=_optional_str(data.get("prelude_sha256")),
        core_sha256=_optional_str(data.get("core_sha256")),
        candidate_path=candidate_path,
        prelude_path=prelude_path,
        core_path=core_path,
        map_path=path,
    )
    if result.enabled and (not prelude_path.exists() or not core_path.exists()):
        return _disabled_result(workdir, "view_files_missing", scene_class=result.scene_class)
    return result


def _write_disabled(workdir: Path, reason: str) -> CoreCandidateViewResult:
    _remove_stale_view_files(workdir)
    result = _disabled_result(workdir, reason)
    try:
        write_json(workdir / CORE_MAP, result.to_dict())
    except OSError:
        return result
    return result


def _disabled_result(workdir: Path, reason: str, *, scene_class: str | None = None) -> CoreCandidateViewResult:
    return CoreCandidateViewResult(
        enabled=False,
        fallback=True,
        reason=reason,
        scene_class=scene_class,
        candidate_path=workdir / "candidate.py",
        prelude_path=workdir / PRELUDE,
        core_path=workdir / CORE_CANDIDATE,
        map_path=workdir / CORE_MAP,
    )


def _remove_stale_view_files(workdir: Path) -> None:
    for filename in (PRELUDE, CORE_CANDIDATE):
        try:
            (workdir / filename).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _class_start_line(node: ast.ClassDef) -> int:
    decorator_lines = [decorator.lineno for decorator in node.decorator_list if hasattr(decorator, "lineno")]
    return min([node.lineno, *decorator_lines])


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path_name(path: Path | None, fallback: str) -> str:
    if path is None:
        return fallback
    return path.name


def _resolve_workdir_path(workdir: Path, raw: object, fallback: str) -> Path:
    if isinstance(raw, str) and raw:
        path = Path(raw)
        return path if path.is_absolute() else workdir / path
    return workdir / fallback


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
