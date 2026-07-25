"""Facts-only adapter over the frozen, previously tested logic engine."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.logic_engine_mvp.logic_engine_mvp.logic_facts import (
    extract_deterministic_logic_facts,
)
from tools.logic_engine_mvp.logic_engine_mvp.review_input import build_review_input

from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._json_values import freeze_json_object, thaw_json_object
from manim_quality.revisions.fingerprint import code_hash

ENGINE_EXTRACTOR_IDENTITY = (
    "logic-engine-mvp@sha256:"
    "bfdcf809d69a125dfb5bd164a5ec16556b944be4d471f8b671009ce3f410149a"
    "/review-evidence-v1"
)

_PROMPT_KEYS = (
    "scene_classes",
    "visible_math_claims",
    "deterministic_logic_facts",
    "focused_code_excerpts",
    "helper_method_excerpts",
)
_REQUIRED_KEYS = frozenset(
    {
        "schema_version",
        "candidate_code_hash",
        "extractor_identity",
        "current_sample_evidence",
        *_PROMPT_KEYS,
        "input_policy",
    }
)
_REPAIR_HINT_KEYS = frozenset(
    {
        "exact_code_after",
        "line_replacements",
        "replacement",
        "replacement_text",
    }
)
_EXTERNAL_DIAGNOSIS_KEYS = frozenset(
    {
        "error_type",
        "expected_outcome",
        "expected_visual_change",
        "repair_policy",
        "visible_error_description",
    }
)
_PROBLEM_FILES = ("question.txt", "problem_text.txt", "problem.md")
_MANIFEST_FILES = ("case_manifest.json", "sample_meta.json")


def build_engine_review_evidence(workspace: Path) -> dict[str, object]:
    root = Path(workspace).resolve(strict=True)
    candidate = _required_child(root, "candidate.py")
    with tempfile.TemporaryDirectory(prefix="manim-quality-logic-evidence-") as temp:
        isolated = Path(temp)
        shutil.copyfile(candidate, isolated / "candidate.py")
        _copy_problem(root, isolated)
        _write_scene_manifest(root, isolated)
        raw = build_review_input(isolated)
    compact = {
        "schema_version": "manim-quality.logic-engine-evidence.v1",
        "candidate_code_hash": _candidate_hash(candidate),
        "extractor_identity": ENGINE_EXTRACTOR_IDENTITY,
        "current_sample_evidence": _safe_current_sample(raw),
        **{key: _strip_repair_hints(raw.get(key)) for key in _PROMPT_KEYS},
        "input_policy": {
            "historical_reports_included": False,
            "external_diagnosis_included": False,
            "repair_hints_included": False,
            "purpose": "current_sample_logic_review_only",
        },
    }
    return thaw_json_object(validate_engine_review_evidence(compact))


def validate_engine_review_evidence(
    value: object, *, expected_code_hash: str | None = None
) -> Mapping[str, object]:
    frozen = freeze_json_object(value, "engine_evidence")
    if frozen.keys() != _REQUIRED_KEYS:
        raise ValueError("engine evidence fields do not match adapter contract")
    if frozen.get("schema_version") != "manim-quality.logic-engine-evidence.v1":
        raise ValueError("engine evidence schema version is unsupported")
    evidence_code_hash = frozen.get("candidate_code_hash")
    require_sha256(evidence_code_hash, "engine evidence candidate_code_hash")
    if expected_code_hash is not None and evidence_code_hash != expected_code_hash:
        raise ValueError("engine evidence does not match candidate code hash")
    if frozen.get("extractor_identity") != ENGINE_EXTRACTOR_IDENTITY:
        raise ValueError("engine evidence extractor identity is unsupported")
    _validate_current_sample(frozen.get("current_sample_evidence"))
    policy = frozen.get("input_policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(key) is not False
        for key in (
            "historical_reports_included",
            "external_diagnosis_included",
            "repair_hints_included",
        )
    ):
        raise ValueError("engine evidence input policy is unsafe")
    if _contains_forbidden_key(frozen):
        raise ValueError("engine evidence contains diagnosis or repair hints")
    return frozen


def verify_engine_review_evidence(
    candidate_code: str, value: object
) -> Mapping[str, object]:
    if type(candidate_code) is not str:
        raise TypeError("candidate_code must be a string")
    frozen = validate_engine_review_evidence(
        value, expected_code_hash=code_hash(candidate_code)
    )
    facts = freeze_json_object(
        extract_deterministic_logic_facts(candidate_code),
        "recomputed deterministic facts",
    )
    if frozen.get("deterministic_logic_facts") != facts:
        raise ValueError("engine evidence deterministic facts do not match candidate")
    actual = freeze_json_object(
        {key: frozen.get(key) for key in _PROMPT_KEYS}, "code-derived evidence"
    )
    if actual != _recompute_code_derived_evidence(candidate_code):
        raise ValueError("engine code-derived evidence does not match candidate")
    return frozen


def _recompute_code_derived_evidence(candidate_code: str) -> Mapping[str, object]:
    with tempfile.TemporaryDirectory(prefix="manim-quality-logic-verify-") as temp:
        root = Path(temp)
        (root / "candidate.py").write_text(candidate_code, encoding="utf-8")
        raw = build_review_input(root)
    return freeze_json_object(
        {key: _strip_repair_hints(raw.get(key)) for key in _PROMPT_KEYS},
        "recomputed code-derived evidence",
    )


def _candidate_hash(path: Path) -> str:
    try:
        return code_hash(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        raise ValueError("candidate.py must be readable UTF-8") from error


def _required_child(root: Path, name: str) -> Path:
    try:
        path = (root / name).resolve(strict=True)
    except OSError as error:
        raise ValueError(
            f"required evidence file cannot be resolved: {name}"
        ) from error
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"required evidence file escapes workspace: {name}")
    return path


def _copy_problem(root: Path, isolated: Path) -> None:
    for name in _PROBLEM_FILES:
        path = root / name
        if path.is_file() and path.resolve().is_relative_to(root):
            shutil.copyfile(path, isolated / name)
            return


def _write_scene_manifest(root: Path, isolated: Path) -> None:
    scene_name = _scene_name(root)
    if scene_name is None:
        return
    content = json.dumps({"scene_name": scene_name}, ensure_ascii=False)
    (isolated / "case_manifest.json").write_text(content, encoding="utf-8")


def _scene_name(root: Path) -> str | None:
    for name in _MANIFEST_FILES:
        path = root / name
        if not path.is_file() or not path.resolve().is_relative_to(root):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        value = payload.get("scene_name") if isinstance(payload, Mapping) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safe_current_sample(raw: Mapping[str, object]) -> dict[str, object]:
    value = raw.get("current_sample_evidence")
    if not isinstance(value, Mapping):
        return {"source": "none"}
    scene_name = value.get("scene_name")
    if isinstance(scene_name, str) and scene_name.strip():
        return {
            "source": "bounded_scene_identity",
            "scene_name": scene_name.strip(),
        }
    return {"source": "none"}


def _strip_repair_hints(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_repair_hints(item)
            for key, item in value.items()
            if str(key) not in _REPAIR_HINT_KEYS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_strip_repair_hints(item) for item in value]
    return value


def _contains_forbidden_key(value: object) -> bool:
    forbidden = _REPAIR_HINT_KEYS | _EXTERNAL_DIAGNOSIS_KEYS
    if isinstance(value, Mapping):
        return any(
            str(key) in forbidden or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _validate_current_sample(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("current_sample_evidence must be an object")
    source = value.get("source")
    if source == "none" and set(value) == {"source"}:
        return
    if source == "bounded_scene_identity" and set(value) == {
        "source",
        "scene_name",
    }:
        scene_name = value.get("scene_name")
        if isinstance(scene_name, str) and scene_name.strip():
            return
    raise ValueError("current_sample_evidence fields are invalid")
