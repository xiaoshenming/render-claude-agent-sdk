"""Independent AST impact analysis for conservative Scene slice reuse."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from manim_quality.revisions.fingerprint import sha256_bytes, sha256_text


@dataclass(frozen=True, slots=True)
class SourceImpact:
    scene_hashes: Mapping[str, str]
    shared_dependency_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scene_hashes",
            MappingProxyType(dict(sorted(self.scene_hashes.items()))),
        )


def analyze_source(source: str, ordered_scene_ids: Sequence[str]) -> SourceImpact:
    """Fingerprint Scenes and all non-Scene top-level dependencies."""
    if not isinstance(source, str):
        raise TypeError("source must be str")
    scene_ids = _validate_scene_ids(ordered_scene_ids)
    tree = ast.parse(source)
    classes = _exact_scene_classes(tree, scene_ids)
    scene_hashes = {scene_id: _node_hash(classes[scene_id]) for scene_id in scene_ids}
    scene_nodes = {id(item) for item in classes.values()}
    shared_body = [node for node in tree.body if id(node) not in scene_nodes]
    shared = ast.Module(body=shared_body, type_ignores=tree.type_ignores)
    canonical = ast.dump(shared, annotate_fields=True, include_attributes=False)
    return SourceImpact(scene_hashes, sha256_text(canonical))


def scene_order_hash(scene_ids: Sequence[str]) -> str:
    payload = json.dumps(
        list(scene_ids), ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def _validate_scene_ids(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("ordered_scene_ids must be a sequence")
    result = tuple(value)
    if not result or any(not isinstance(item, str) or not item for item in result):
        raise ValueError("ordered_scene_ids must contain non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError("ordered_scene_ids must not contain duplicates")
    return result


def _exact_scene_classes(
    tree: ast.Module, scene_ids: tuple[str, ...]
) -> dict[str, ast.ClassDef]:
    classes: dict[str, list[ast.ClassDef]] = {name: [] for name in scene_ids}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in classes:
            classes[node.name].append(node)
    invalid = [name for name, matches in classes.items() if len(matches) != 1]
    if invalid:
        raise ValueError(f"ordered Scene IDs must name one top-level class: {invalid}")
    return {name: matches[0] for name, matches in classes.items()}


def _node_hash(node: ast.AST) -> str:
    canonical = ast.dump(node, annotate_fields=True, include_attributes=False)
    return sha256_text(canonical)
