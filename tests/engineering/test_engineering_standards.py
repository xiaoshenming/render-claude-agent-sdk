from pathlib import Path

import pytest

from scripts.check_engineering_standards import check_workspace


def test_workspace_meets_engineering_standards() -> None:
    root = Path(__file__).parents[2]

    assert check_workspace(root) == []


def test_checker_rejects_long_production_file(tmp_path: Path) -> None:
    source = tmp_path / "src" / "manim_quality" / "too_long.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n" * 301, encoding="utf-8")

    violations = check_workspace(tmp_path)

    assert any("too_long.py" in item and "300 lines" in item for item in violations)


def test_checker_rejects_long_function(tmp_path: Path) -> None:
    source = tmp_path / "src" / "manim_quality" / "long_function.py"
    source.parent.mkdir(parents=True)
    body = "\n".join(f"    value_{index} = {index}" for index in range(61))
    source.write_text(f"def too_long():\n{body}\n", encoding="utf-8")

    violations = check_workspace(tmp_path)

    assert any("too_long" in item and "60 lines" in item for item in violations)


def test_checker_rejects_legacy_application_import(tmp_path: Path) -> None:
    source = tmp_path / "src" / "manim_quality" / "legacy_import.py"
    source.parent.mkdir(parents=True)
    source.write_text("from apps.render import worker\n", encoding="utf-8")

    violations = check_workspace(tmp_path)

    assert any("forbidden legacy import apps.render" in item for item in violations)


@pytest.mark.parametrize(
    "statement, expected",
    [
        ("from apps import render\n", "forbidden legacy import apps"),
        ("from app import workers\n", "forbidden legacy import app"),
    ],
)
def test_checker_rejects_legacy_root_aliases(
    tmp_path: Path,
    statement: str,
    expected: str,
) -> None:
    source = tmp_path / "src" / "manim_quality" / "legacy_alias.py"
    source.parent.mkdir(parents=True)
    source.write_text(statement, encoding="utf-8")

    violations = check_workspace(tmp_path)

    assert any(expected in item for item in violations)


def test_generated_named_subdirectory_does_not_bypass_limits(tmp_path: Path) -> None:
    source = tmp_path / "src" / "manim_quality" / "generated" / "large.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n" * 301, encoding="utf-8")

    violations = check_workspace(tmp_path)

    assert any("generated/large.py" in item for item in violations)


def test_hard_limits_are_inclusive(tmp_path: Path) -> None:
    source = tmp_path / "src" / "manim_quality" / "at_limit.py"
    source.parent.mkdir(parents=True)
    body = "\n".join(f"    value_{index} = {index}" for index in range(59))
    padding = "\n".join("value = 1" for _ in range(240))
    source.write_text(f"def at_limit():\n{body}\n{padding}\n", encoding="utf-8")

    assert len(source.read_text(encoding="utf-8").splitlines()) == 300
    assert check_workspace(tmp_path) == []


def test_harness_contract_is_root_entrypoint() -> None:
    root = Path(__file__).parents[2]
    contract = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "Only the Quality Orchestrator" in contract
    assert "Deny Bash" in contract
    assert "Hard limit: 300" in contract
