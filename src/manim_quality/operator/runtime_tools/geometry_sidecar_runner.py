"""Tee wrapper around the frozen layout probe runner.

The frozen probe computes per-object stroke geometry internally but drops it
from its stdout payload. This standalone script (stdlib only; it runs inside
the Manim worker interpreter) loads the frozen runner, tees the objects that
``_collect_objects`` already produced into a geometry sidecar file, and then
lets the frozen ``main`` run unchanged. Classification, stdout contract, and
exit code of the frozen runner are never altered; a failed tee or sidecar
write only means the versioned layout policy later fails closed.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path

SIDECAR_VERSION = 1
DELEGATE_ENV = "MANIM_LAYOUT_PROBE_DELEGATE"
SIDECAR_ENV = "MANIM_LAYOUT_PROBE_SIDECAR_PATH"


def _load_delegate(path: Path):
    # The frozen runner is materialized as ``probe_runner.txt``; the explicit
    # SourceFileLoader lets importlib execute it despite the non-.py suffix.
    loader = importlib.machinery.SourceFileLoader("_layout_probe_delegate", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load layout probe delegate: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "main", None)):
        raise RuntimeError(f"layout probe delegate has no main(): {path}")
    from manim_quality.operator.runtime_tools.display_bounds import install_complete_bounds
    install_complete_bounds(module)
    return module


def _shape_records(items: object) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not isinstance(items, list):
        return records
    for item in items:
        if not isinstance(item, dict) or item.get("kind") != "shape":
            continue
        geometry = item.get("geometry")
        if isinstance(geometry, dict):
            records.append(
                {
                    "path": item.get("path"),
                    "class": item.get("class"),
                    "geometry": geometry,
                }
            )
    return records


def _install_tee(module, captures: list[dict[str, object]]) -> None:
    original = getattr(module, "_collect_objects", None)
    if not callable(original):
        return  # unknown runner variant: no capture, policy fails closed

    def teeing_collect_objects(scene):
        items = original(scene)
        try:
            captures.append(
                {
                    "step": getattr(scene, "_layout_probe_step", 0),
                    "shapes": _shape_records(items),
                }
            )
        except Exception:  # noqa: BLE001 - capture must never break the probe
            pass
        return items

    module._collect_objects = teeing_collect_objects


def _write_sidecar(path: str, captures: list[dict[str, object]]) -> None:
    try:
        Path(path).write_text(
            json.dumps(
                {"version": SIDECAR_VERSION, "captures": captures},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        print(f"geometry sidecar write failed: {error}", file=sys.stderr)


def main() -> int:
    delegate_path = os.environ.get(DELEGATE_ENV)
    if not delegate_path:
        print(f"{DELEGATE_ENV} is required", file=sys.stderr)
        return 2
    module = _load_delegate(Path(delegate_path))
    sidecar_path = os.environ.get(SIDECAR_ENV)
    captures: list[dict[str, object]] = []
    if sidecar_path:
        _install_tee(module, captures)
    code = int(module.main())
    if sidecar_path:
        _write_sidecar(sidecar_path, captures)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
