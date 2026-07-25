"""Conservative delta scan for newly introduced Scene-level capabilities."""

from __future__ import annotations

import ast

from ..diff_guard import DiffGuardResult

_DYNAMIC_CALLS = frozenset(
    {"__import__", "compile", "delattr", "eval", "exec", "getattr", "setattr"}
)
_FILE_CALLS = frozenset(
    {
        "open",
        "read_bytes",
        "read_text",
        "rmdir",
        "unlink",
        "write_bytes",
        "write_text",
    }
)
_PROCESS_CALLS = frozenset(
    {"Popen", "call", "check_call", "check_output", "popen", "run", "system"}
)
_ASSET_CALLS = frozenset(
    {"ImageMobject", "OpenGLImageMobject", "SVGMobject", "VideoMobject"}
)
_MODULE_RISKS = {
    "os": "process",
    "subprocess": "process",
    "shutil": "file_io",
    "pathlib": "file_io",
    "requests": "network",
    "httpx": "network",
    "socket": "network",
    "urllib": "network",
}


def new_scene_risks(before: str, after: str, diff: DiffGuardResult) -> tuple[str, ...]:
    before_tree, after_tree = ast.parse(before), ast.parse(after)
    before_classes = _classes(before_tree)
    after_classes = _classes(after_tree)
    before_aliases, after_aliases = _aliases(before_tree), _aliases(after_tree)
    new: set[str] = set()
    for scene_id in diff.changed_scene_ids:
        old = _signals(before_classes[scene_id], before_aliases)
        current = _signals(after_classes[scene_id], after_aliases)
        new.update(kind for kind, _signature in current - old)
    return tuple(sorted(new))


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _aliases(tree: ast.Module) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for item in node.names:
                values[item.asname or item.name.split(".")[0]] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                values[item.asname or item.name] = f"{node.module}.{item.name}"
    return values


def _signals(node: ast.ClassDef, aliases: dict[str, str]) -> set[tuple[str, str]]:
    aliases = _local_aliases(node, aliases)
    signals: set[tuple[str, str]] = set()
    for item in ast.walk(node):
        kind = _risk_kind(item, aliases)
        if kind is not None:
            signature = ast.dump(item, annotate_fields=True, include_attributes=False)
            signals.add((kind, signature))
    return signals


def _local_aliases(node: ast.ClassDef, aliases: dict[str, str]) -> dict[str, str]:
    values = dict(aliases)
    assignments = [item for item in ast.walk(node) if isinstance(item, ast.Assign)]
    for _pass in range(2):
        for item in assignments:
            if len(item.targets) != 1 or not isinstance(item.targets[0], ast.Name):
                continue
            path = _call_path(item.value, values)
            if path:
                values[item.targets[0].id] = path
    return values


def _risk_kind(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return "shared_state"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "local_import"
    if isinstance(node, ast.Call):
        target = node.func
    elif isinstance(node, (ast.Attribute, ast.Name)):
        target = node
    else:
        return None
    path = _call_path(target, aliases)
    name = path.rsplit(".", 1)[-1]
    root = path.split(".", 1)[0]
    if name in _DYNAMIC_CALLS or "__" in path:
        return "dynamic_code"
    if name in _FILE_CALLS:
        return "file_io"
    if name in _PROCESS_CALLS and isinstance(node, (ast.Call, ast.Attribute)):
        return "process"
    if name in _ASSET_CALLS:
        return "asset_dependency"
    return _MODULE_RISKS.get(root)


def _call_path(node: ast.expr, aliases: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _call_path(node.value, aliases)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _call_path(node.func, aliases)
    return ""
