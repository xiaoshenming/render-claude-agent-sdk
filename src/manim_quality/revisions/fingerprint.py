"""Canonical content hashes and conservative Python AST fingerprints."""

from __future__ import annotations

import ast
import hashlib
from types import MappingProxyType

HASH_PREFIX = "sha256:"


class PythonSyntaxError(ValueError):
    """Raised when source cannot be represented by a Python AST."""

    def __init__(self, error: SyntaxError) -> None:
        location = f"line {error.lineno}"
        if error.offset is not None:
            location += f", column {error.offset}"
        super().__init__(f"invalid Python source at {location}: {error.msg}")


def sha256_bytes(content: bytes) -> str:
    """Return a canonical SHA-256 identity for bytes."""
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    return f"{HASH_PREFIX}{hashlib.sha256(content).hexdigest()}"


def sha256_text(content: str) -> str:
    """Return the UTF-8 SHA-256 identity for text."""
    if not isinstance(content, str):
        raise TypeError("content must be str")
    return sha256_bytes(content.encode("utf-8"))


def evidence_hash(content: bytes) -> str:
    """Hash the exact serialized evidence artifact bytes."""
    return sha256_bytes(content)


def code_hash(source: str) -> str:
    """Hash the complete source text without normalization."""
    return sha256_text(source)


def semantic_fingerprint(source: str) -> str:
    """Hash every semantic AST field while excluding source locations."""
    return _node_hash(_parse(source))


def scene_fingerprints(source: str) -> MappingProxyType[str, str]:
    """Hash each locally identifiable Scene class in stable name order."""
    tree = _parse(source)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    scene_names = _scene_class_names(classes)
    fingerprints = {name: _node_hash(classes[name]) for name in sorted(scene_names)}
    return MappingProxyType(fingerprints)


def _parse(source: str) -> ast.Module:
    if not isinstance(source, str):
        raise TypeError("source must be str")
    try:
        return ast.parse(source)
    except SyntaxError as error:
        raise PythonSyntaxError(error) from error


def _node_hash(node: ast.AST) -> str:
    canonical = ast.dump(node, annotate_fields=True, include_attributes=False)
    return sha256_text(canonical)


def _scene_class_names(classes: dict[str, ast.ClassDef]) -> set[str]:
    names = {
        name
        for name, node in classes.items()
        if _declares_construct(node) or any(_is_scene_base(base) for base in node.bases)
    }
    changed = True
    while changed:
        before = len(names)
        names.update(
            name
            for name, node in classes.items()
            if any(_base_name(base) in names for base in node.bases)
        )
        changed = len(names) != before
    return names


def _declares_construct(node: ast.ClassDef) -> bool:
    return any(
        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "construct"
        for item in node.body
    )


def _is_scene_base(node: ast.expr) -> bool:
    name = _base_name(node)
    return name is not None and name.endswith("Scene")


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
