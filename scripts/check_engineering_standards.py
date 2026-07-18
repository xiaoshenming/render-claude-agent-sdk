"""Machine-checkable source size limits for the quality platform."""

from __future__ import annotations

import ast
from pathlib import Path

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 60
SOURCE_ROOTS = ("src", "apps", "scripts")
FORBIDDEN_IMPORT_PREFIXES = ("app", "apps", "shuxuepai")


def check_workspace(root: Path) -> list[str]:
    """Return deterministic engineering-standard violations under ``root``."""
    violations: list[str] = []
    for source in _python_sources(root):
        violations.extend(_check_source(root, source))
    return sorted(violations)


def _python_sources(root: Path) -> list[Path]:
    sources: list[Path] = []
    for name in SOURCE_ROOTS:
        source_root = root / name
        if not source_root.exists():
            continue
        sources.extend(source_root.rglob("*.py"))
    return sorted(sources)


def _check_source(root: Path, source: Path) -> list[str]:
    relative = source.relative_to(root).as_posix()
    text = source.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    violations: list[str] = []
    if line_count > MAX_FILE_LINES:
        violations.append(
            f"{relative}: {line_count} lines exceeds hard limit of "
            f"{MAX_FILE_LINES} lines"
        )

    try:
        tree = ast.parse(text, filename=str(source))
    except SyntaxError as error:
        violations.append(f"{relative}: cannot inspect invalid Python: {error.msg}")
        return violations

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_check_function(relative, node))
    violations.extend(_check_imports(relative, tree))
    return violations


def _check_function(
    relative: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    end_line = node.end_lineno or node.lineno
    line_count = end_line - node.lineno + 1
    if line_count <= MAX_FUNCTION_LINES:
        return []
    return [
        f"{relative}:{node.lineno} function {node.name} has {line_count} lines; "
        f"hard limit is {MAX_FUNCTION_LINES} lines"
    ]


def _check_imports(relative: str, tree: ast.AST) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if _is_forbidden_import(name):
                violations.append(
                    f"{relative}:{node.lineno} forbidden legacy import {name}"
                )
    return violations


def _is_forbidden_import(name: str) -> bool:
    return any(
        name == prefix or name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_IMPORT_PREFIXES
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = check_workspace(root)
    if not violations:
        print("Engineering standards: PASS")
        return 0
    print("Engineering standards: FAIL")
    for violation in violations:
        print(f"- {violation}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
