"""Verified external artifact manifests for frozen logic evaluation sets."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._validation import require_non_empty_string
from manim_quality.revisions.fingerprint import sha256_bytes

from .shadow import EvalTruth

SCHEMA_VERSION = "manim-quality.logic-eval.v1"
_SAMPLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class EvalManifestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvalArtifact:
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        require_non_empty_string(self.relative_path, "relative_path")
        require_sha256(self.sha256, "sha256")
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("evaluation artifact path must be relative and contained")

    def resolve_verified(self, root: Path) -> Path:
        base = Path(root).resolve(strict=True)
        try:
            path = (base / self.relative_path).resolve(strict=True)
        except OSError as error:
            message = f"missing evaluation artifact: {self.relative_path}"
            raise EvalManifestError(message) from error
        if not path.is_relative_to(base) or not path.is_file():
            message = f"evaluation artifact escapes root: {self.relative_path}"
            raise EvalManifestError(message)
        if sha256_bytes(path.read_bytes()) != self.sha256:
            message = f"evaluation artifact hash mismatch: {self.relative_path}"
            raise EvalManifestError(message)
        return path


@dataclass(frozen=True, slots=True)
class FrozenEvalCase:
    sample_id: str
    truth: EvalTruth
    artifacts: Mapping[str, EvalArtifact | None]
    expected_issue_type: str | None = None
    difficulty: str | None = None
    target_lines: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not _SAMPLE_ID.fullmatch(self.sample_id) or ".." in self.sample_id:
            raise EvalManifestError("sample_id must be a safe identifier")
        if any(type(line) is not int or line < 1 for line in self.target_lines):
            raise EvalManifestError("target_lines must contain positive integers")
        object.__setattr__(self, "target_lines", tuple(self.target_lines))


@dataclass(frozen=True, slots=True)
class FrozenEvalManifest:
    pack_id: str
    truth: EvalTruth
    source_manifest: EvalArtifact
    cases: tuple[FrozenEvalCase, ...]
    private_ground_truth: EvalArtifact | None = None


def load_frozen_eval_manifest(
    manifest_path: Path, *, dataset_root: Path, verify_artifacts: bool = True
) -> FrozenEvalManifest:
    data = _object(
        json.loads(Path(manifest_path).read_text(encoding="utf-8")), "manifest"
    )
    if data.get("schema_version") != SCHEMA_VERSION or data.get("frozen") is not True:
        raise EvalManifestError("evaluation manifest is not a supported frozen schema")
    truth = _truth(data.get("truth"))
    source = _artifact(data.get("source_manifest"), "source_manifest")
    private = data.get("private_ground_truth")
    private_artifact = (
        _artifact(private, "private_ground_truth") if private is not None else None
    )
    cases = tuple(_case(item, truth) for item in _array(data.get("samples"), "samples"))
    if data.get("sample_count") != len(cases):
        raise EvalManifestError("sample_count does not match samples")
    if len({case.sample_id for case in cases}) != len(cases):
        raise EvalManifestError("sample_id values must be unique")
    manifest = FrozenEvalManifest(
        pack_id=_text(data.get("pack_id"), "pack_id"),
        truth=truth,
        source_manifest=source,
        cases=cases,
        private_ground_truth=private_artifact,
    )
    if verify_artifacts:
        _verify_manifest(manifest, dataset_root)
    return manifest


def _case(value: object, truth: EvalTruth) -> FrozenEvalCase:
    data = _object(value, "sample")
    if _truth(data.get("truth")) is not truth:
        raise EvalManifestError("sample truth differs from pack truth")
    artifacts = {
        _text(name, "artifact name"): (
            _artifact(item, f"artifact {name}") if item is not None else None
        )
        for name, item in _object(data.get("artifacts"), "artifacts").items()
    }
    target_lines = _positive_ints(data.get("target_lines", []), "target_lines")
    if truth is EvalTruth.KNOWN_BAD and not target_lines:
        raise EvalManifestError("known-bad sample requires target_lines")
    return FrozenEvalCase(
        sample_id=_text(data.get("sample_id"), "sample_id"),
        truth=truth,
        artifacts=artifacts,
        expected_issue_type=_optional_text(data.get("expected_issue_type")),
        difficulty=_optional_text(data.get("difficulty")),
        target_lines=target_lines,
    )


def _verify_manifest(manifest: FrozenEvalManifest, root: Path) -> None:
    manifest.source_manifest.resolve_verified(root)
    if manifest.private_ground_truth is not None:
        manifest.private_ground_truth.resolve_verified(root)
    for case in manifest.cases:
        for artifact in case.artifacts.values():
            if artifact is not None:
                artifact.resolve_verified(root)


def _artifact(value: object, name: str) -> EvalArtifact:
    data = _object(value, name)
    return EvalArtifact(
        relative_path=_text(data.get("path"), f"{name}.path"),
        sha256=_text(data.get("sha256"), f"{name}.sha256"),
    )


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise EvalManifestError(f"{name} must be a JSON object")
    return value


def _array(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise EvalManifestError(f"{name} must be a JSON array")
    return value


def _truth(value: object) -> EvalTruth:
    try:
        return EvalTruth(value)
    except (TypeError, ValueError) as error:
        raise EvalManifestError(f"invalid evaluation truth: {value!r}") from error


def _text(value: object, name: str) -> str:
    try:
        return require_non_empty_string(value, name)
    except (TypeError, ValueError) as error:
        raise EvalManifestError(str(error)) from error


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value, "optional text")


def _positive_ints(value: object, name: str) -> tuple[int, ...]:
    items = _array(value, name)
    if any(type(item) is not int or item < 1 for item in items):
        raise EvalManifestError(f"{name} must contain positive integers")
    return tuple(items)
