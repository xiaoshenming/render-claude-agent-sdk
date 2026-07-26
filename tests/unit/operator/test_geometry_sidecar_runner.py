"""Sidecar tee wrapper: frozen probe output unchanged, geometry captured."""

import json
import os
import subprocess
import sys
from pathlib import Path

from manim_quality.operator.runtime_tools import geometry_sidecar_runner

WRAPPER = Path(geometry_sidecar_runner.__file__).resolve()

FAKE_DELEGATE = '''
import json
from types import SimpleNamespace


def _collect_objects(scene):
    return [
        {
            "path": "mobjects.2",
            "class": "Polygon",
            "kind": "shape",
            "bbox": {"left": -1.0},
            "geometry": {"type": "polygon", "points": [[0.0, 1.0], [1.0, 0.0], [-1.0, 0.0]]},
        },
        {"path": "mobjects.12", "class": "MathTex", "kind": "formula", "bbox": {}},
        {"path": "mobjects.3", "class": "Line", "kind": "shape", "bbox": {}},
    ]


def main() -> int:
    items = _collect_objects(SimpleNamespace(_layout_probe_step=11))
    print(json.dumps({"scene": "Solution", "object_count": len(items)}))
    return 0
'''


def _run(tmp_path: Path, delegate_source: str, *, env_overrides=None) -> tuple[subprocess.CompletedProcess, Path]:
    # The real frozen runner is materialized with a .txt suffix.
    delegate = tmp_path / "delegate.txt"
    delegate.write_text(delegate_source, encoding="utf-8")
    sidecar = tmp_path / "geometry_sidecar.json"
    env = {
        **os.environ,
        "MANIM_LAYOUT_PROBE_DELEGATE": str(delegate),
        "MANIM_LAYOUT_PROBE_SIDECAR_PATH": str(sidecar),
        **(env_overrides or {}),
    }
    result = subprocess.run(
        [sys.executable, str(WRAPPER)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result, sidecar


def test_wrapper_preserves_stdout_and_captures_shape_geometry(tmp_path: Path) -> None:
    result, sidecar = _run(tmp_path, FAKE_DELEGATE)

    assert result.returncode == 0
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "scene": "Solution",
        "object_count": 3,
    }
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["captures"] == [
        {
            "step": 11,
            "shapes": [
                {
                    "path": "mobjects.2",
                    "class": "Polygon",
                    "geometry": {
                        "type": "polygon",
                        "points": [[0.0, 1.0], [1.0, 0.0], [-1.0, 0.0]],
                    },
                }
            ],
        }
    ]


def test_wrapper_survives_delegate_without_collect_objects(tmp_path: Path) -> None:
    result, sidecar = _run(
        tmp_path,
        "def main() -> int:\n    print('{}')\n    return 0\n",
    )

    assert result.returncode == 0
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["captures"] == []


def test_frozen_runner_exposes_the_tee_contract() -> None:
    """The frozen probe_runner.txt must expose the exact symbols the tee
    wrapper relies on: a renamed _collect_objects would silently disable
    geometry capture and fail the policy closed forever, and a module-level
    manim import would break loading outside a worker interpreter. Checked
    statically because unit environments do not ship numpy/manim."""
    import ast

    frozen = WRAPPER.parents[4] / "vendor" / "layout_probe" / "probe_runner.txt"
    tree = ast.parse(frozen.read_text(encoding="utf-8"))

    top_level_defs = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert {"main", "_collect_objects"} <= top_level_defs
    top_level_imports = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "manim" not in top_level_imports


def test_wrapper_requires_delegate_env(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items()}
    env.pop("MANIM_LAYOUT_PROBE_DELEGATE", None)
    result = subprocess.run(
        [sys.executable, str(WRAPPER)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 2
    assert "MANIM_LAYOUT_PROBE_DELEGATE" in result.stderr
