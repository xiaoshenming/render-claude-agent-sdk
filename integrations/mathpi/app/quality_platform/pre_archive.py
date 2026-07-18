"""Fail-open bridge from renderable FAST_PRE code to the quality platform."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings

from .sdk_review import run_sdk_logic_review
from .retention import build_review_retention

_SCHEMA_VERSION = "mathpi.pre-archive-quality.v1"
_UPSTREAM_HEAD = "18a94aed86047f2069eb1b9d277cbfdf2e1f8980"
_PLATFORM_ROOT = Path(__file__).resolve().parents[2] / "manim_quality_platform"
_PLATFORM_SOURCE = _PLATFORM_ROOT / "src"


@dataclass(frozen=True, slots=True)
class PreArchiveQualityRequest:
    job_id: str
    candidate_code: str
    scene_names: tuple[str, ...]
    problem_text: str
    expected_solution: str
    artifact_root: Path
    enabled: bool = True
    attempt_id: str = ""


@dataclass(frozen=True, slots=True)
class PreArchiveQualityResult:
    selected_code: str
    selected_code_hash: str
    status: str
    fail_open_used: bool
    manifest_path: Path | None
    retention: dict[str, Any]


def run_pre_archive_quality_platform(
    request: PreArchiveQualityRequest,
) -> PreArchiveQualityResult:
    """Record platform evidence and return the code that may proceed to archive."""
    code = str(request.candidate_code or "")
    if not code.strip():
        raise ValueError("candidate_code must not be empty")
    code_hash = _sha256_text(code)
    if not request.enabled:
        retention = build_review_retention(
            model="",
            status="disabled",
            review=None,
            candidate_code_hash=code_hash,
            selected_code_hash=code_hash,
            fail_open=False,
        )
        return PreArchiveQualityResult(
            code, code_hash, "disabled", False, None, retention
        )

    attempt_id = request.attempt_id.strip() or uuid.uuid4().hex
    run_dir = request.artifact_root / request.job_id / attempt_id
    manifest_path = run_dir / "manifest.json"
    base = _manifest_base(request, code_hash)
    try:
        evidence = _build_symbolic_evidence(code, request.scene_names)
        review = run_sdk_logic_review(
            code=code,
            problem_text=request.problem_text,
            expected_solution=request.expected_solution,
        )
        status = "review_recorded" if review is not None else "evidence_recorded"
        retention = build_review_retention(
            model=settings.MANIM_QUALITY_MODEL if review is not None else "",
            status=status,
            review=review,
            candidate_code_hash=code_hash,
            selected_code_hash=code_hash,
            fail_open=False,
        )
        payload = {
            **base,
            "evidence": evidence,
            "review": {
                "decision": retention["decision"],
                "summary": retention["summary"],
                "issues": retention["issues"],
            } if review is not None else None,
            "retention": retention,
            "output": _output(code_hash, status, False),
        }
        _write_artifacts(run_dir, code, payload)
        return PreArchiveQualityResult(
            code, code_hash, status, False, manifest_path, retention
        )
    except Exception as exc:  # noqa: BLE001 - playable code must survive.
        error = f"{type(exc).__name__}: {exc}"[:1000]
        retention = build_review_retention(
            model=settings.MANIM_QUALITY_MODEL,
            status="fail_open",
            review=None,
            candidate_code_hash=code_hash,
            selected_code_hash=code_hash,
            fail_open=True,
            error=error,
        )
        payload = {
            **base,
            "evidence": {"symbolic_scene_count": 0, "scenes": []},
            "retention": retention,
            "output": {
                **_output(code_hash, "fail_open", True),
                "error_type": type(exc).__name__,
                "error": retention["error"],
            },
        }
        try:
            _write_artifacts(run_dir, code, payload)
            stored_manifest: Path | None = manifest_path
        except OSError:
            stored_manifest = None
        return PreArchiveQualityResult(
            code, code_hash, "fail_open", True, stored_manifest, retention
        )


def _build_symbolic_evidence(code: str, scene_names: tuple[str, ...]) -> dict[str, Any]:
    source = str(_PLATFORM_SOURCE)
    if source not in sys.path:
        sys.path.insert(0, source)
    from manim_quality.logic.expectations.symbolic_index import build_symbolic_index

    names = tuple(name for name in scene_names if str(name).strip())
    if not names:
        names = _scene_names_from_code(code)
    scenes: list[dict[str, Any]] = []
    for scene_name in names:
        index = build_symbolic_index(code, scene_id=scene_name)
        scenes.append(
            {
                "scene_id": scene_name,
                "point_count": len(index.points),
                "line_count": len(index.lines),
                "points": sorted(index.points),
                "lines": sorted(index.lines),
            }
        )
    return {"symbolic_scene_count": len(scenes), "scenes": scenes}


def _scene_names_from_code(code: str) -> tuple[str, ...]:
    tree = ast.parse(code)
    names = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(base, "id", "") for base in node.bases}
        if bases.intersection({"Scene", "ThreeDScene", "MovingCameraScene"}):
            names.append(node.name)
    if not names:
        raise ValueError("no renderable Scene found")
    return tuple(names)


def _manifest_base(
    request: PreArchiveQualityRequest, code_hash: str
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "job_id": request.job_id,
        "platform": {
            "source_head": _UPSTREAM_HEAD,
            "mode": "pre_archive_sdk_review_fail_open",
        },
        "input": {
            "candidate_code_hash": code_hash,
            "scene_names": list(request.scene_names),
            "problem_text_hash": _sha256_text(request.problem_text),
            "expected_solution_hash": _sha256_text(request.expected_solution),
        },
    }


def _output(code_hash: str, status: str, fail_open: bool) -> dict[str, Any]:
    return {
        "status": status,
        "selected_code_hash": code_hash,
        "code_changed": False,
        "fail_open_used": fail_open,
        "archive_allowed": True,
    }


def _write_artifacts(run_dir: Path, code: str, payload: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(run_dir / "candidate_before.py", code)
    _atomic_write(run_dir / "candidate_selected.py", code)
    _atomic_write(
        run_dir / "manifest.json",
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
