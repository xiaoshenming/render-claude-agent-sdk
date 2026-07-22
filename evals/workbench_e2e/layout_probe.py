from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .process_env import sanitized_subprocess_env
from .rendering import scene_name


class LocalLayoutProbeChecker:
    def __init__(self, config, check_result_type: type) -> None:
        self._config = config
        self._check_result_type = check_result_type
        self.last_probe: dict[str, Any] = {}
        self.last_payload: dict[str, Any] = {}
        self._calls = 0

    def run_check(self, code_path: Path, workdir: Path):
        self._calls += 1
        call_dir = workdir / f"local_layout_probe_{self._calls:02d}"
        call_dir.mkdir(parents=True, exist_ok=True)
        runner = call_dir / "probe_runner.py"
        runner.write_text(
            _probe_source(self._config.probe_source_path, workdir / "shared_manim_media"),
            encoding="utf-8",
        )
        command = [
            self._config.python,
            str(runner),
            str(code_path.resolve()),
            "--scene",
            scene_name(code_path.read_text(encoding="utf-8")),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._config.timeout_seconds,
                check=False,
                env=sanitized_subprocess_env(),
            )
            (call_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
            (call_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
            probe = normalize_probe(
                parse_probe_stdout(completed.stdout), completed.returncode
            )
        except (subprocess.TimeoutExpired, ValueError) as error:
            return self._check_result_type.failure(f"layout_probe_error:{error}")
        self.last_probe = probe
        payload = payload_from_probe(self._config.vendor_root, probe)
        self.last_payload = payload
        _write_json(call_dir / "layout_probe.json", probe)
        _write_json(call_dir / "check_result.json", payload)
        if not payload.get("ok"):
            return self._check_result_type.failure(str(payload.get("error")))
        return self._check_result_type(
            ok=True,
            passed=bool(payload.get("passed")),
            blocking_count=int(payload.get("blocking_count", 0)),
            issues=list(payload.get("issues") or []),
            raw=dict(payload.get("raw") or {}),
        )


def parse_probe_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("layout probe produced no JSON")


def normalize_probe(probe: dict[str, Any], returncode: int) -> dict[str, Any]:
    normalized = dict(probe)
    normalized["returncode"] = returncode
    if returncode != 0:
        normalized["ok"] = False
        normalized.setdefault("error", f"layout_probe_exit:{returncode}")
    elif "ok" not in normalized:
        errors = normalized.get("errors")
        normalized["ok"] = (
            returncode == 0
            and normalized.get("error_count") == 0
            and isinstance(errors, list)
            and not errors
        )
    return normalized


def build_layout_context(root: Path, check: dict, probe: dict) -> dict:
    module = _vendor_import(root, "tools.quality_repair_checkers.layout_context")
    return module.build_layout_context(check, probe)


def configure_vendor_sdk(config) -> None:
    values = dict(config.provider_env or {})
    values["QUALITY_REPAIR_SDK_MODEL"] = config.model
    runner = _vendor_import(config.vendor_root, "libs.quality_repair.agent.runner")
    runner._load_persistent_sdk_env = lambda: dict(values)


def payload_from_probe(root: Path, probe: dict[str, Any]) -> dict[str, Any]:
    module = _vendor_import(root, "tools.quality_repair_checkers.layout_probe_check")
    return module.payload_from_probe(probe)


def _probe_source(path: Path, media_dir: Path) -> str:
    source = _load_probe_source(path)
    if not isinstance(source, str) or not source.strip():
        raise ValueError("probe source file does not define PROBE_RUNNER_SOURCE")
    marker = 'config.media_dir = "/tmp/manim_layout_probe_media"'
    replacement = f"config.media_dir = {str(media_dir.resolve())!r}"
    return source.replace(marker, replacement)


def _load_probe_source(path: Path) -> object:
    """Load both the legacy single-file probe and the split probe package."""
    parts_path = path.with_name("probe_runner_parts.py")
    if parts_path.is_file():
        spec = importlib.util.spec_from_file_location(
            f"manim_quality_probe_parts_{id(parts_path)}", parts_path
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load probe source module: {parts_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        factory = getattr(module, "probe_runner_source", None)
        if callable(factory):
            return factory()
    scope: dict[str, Any] = {"__name__": "manim_quality_embedded_probe"}
    text = path.read_text(encoding="utf-8")
    exec(compile(text, str(path), "exec"), scope)
    return scope.get("PROBE_RUNNER_SOURCE")


def _vendor_import(root: Path, module: str):
    root_text = str(root.resolve())
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return importlib.import_module(module)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
