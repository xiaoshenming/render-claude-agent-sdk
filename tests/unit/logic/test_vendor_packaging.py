from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHIM = "src/manim_quality/logic/_vendor_package_init.py"
TARGET = "tools/logic_engine_mvp/logic_engine_mvp/__init__.py"


def test_wheel_uses_side_effect_free_logic_engine_package_init() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = config["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    assert force_include[SHIM] == TARGET
    tree = ast.parse((ROOT / SHIM).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)
    )
