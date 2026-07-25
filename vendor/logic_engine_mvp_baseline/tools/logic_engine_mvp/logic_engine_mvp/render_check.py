from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence


def discover_scene_classes(code_path: Path) -> list[str]:
    tree = ast.parse(Path(code_path).read_text(encoding="utf-8", errors="replace"))
    scene_names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name == "BaseConfigScene":
            continue
        if not _has_construct(node):
            continue
        if _looks_like_scene_class(node):
            scene_names.append(node.name)
    return scene_names


def run_render_check(
    case_dir: Path,
    *,
    command: Sequence[str] | None = None,
    scene_names: Sequence[str] | None = None,
    contract_path: Path | None = None,
    affected_only: bool = False,
    quality: str = "l",
    timeout_sec: int = 300,
    out_path: Path | None = None,
) -> dict[str, Any]:
    case_dir = Path(case_dir)
    candidate = case_dir / "candidate.py"
    out = out_path or case_dir / "render_check.json"
    started = time.monotonic()

    if command is None:
        if scene_names is not None:
            scenes = list(scene_names)
        elif affected_only:
            scenes = affected_scene_classes(candidate, contract_path or case_dir / "repair_contract.json")
        else:
            scenes = discover_scene_classes(candidate)
        command = _default_manim_command(candidate, scenes, quality=quality, media_dir=_short_media_dir(case_dir))
    else:
        scenes = list(scene_names or [])
    env = _render_env(candidate)

    try:
        completed = subprocess.run(
            list(command),
            cwd=case_dir,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
        result = {
            "checked": True,
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "timed_out": False,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "candidate": str(candidate),
            "scenes": scenes,
            "command": list(command),
            "tts_shim_enabled": True,
            "asset_shim_enabled": True,
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "checked": True,
            "passed": False,
            "exit_code": "",
            "timed_out": True,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "candidate": str(candidate),
            "scenes": scenes,
            "command": list(command),
            "tts_shim_enabled": True,
            "asset_shim_enabled": True,
            "stdout_tail": _tail(_decode_output(exc.stdout)),
            "stderr_tail": _tail(_decode_output(exc.stderr)),
            "error": f"render command timed out after {timeout_sec}s",
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def affected_scene_classes(code_path: Path, contract_path: Path) -> list[str]:
    source_lines = _contract_source_lines(contract_path)
    if not source_lines:
        return discover_scene_classes(code_path)

    ranges = _scene_class_ranges(code_path)
    affected: list[str] = []
    for scene_name, start, end in ranges:
        if any(start <= line <= end for line in source_lines):
            affected.append(scene_name)
    return affected or discover_scene_classes(code_path)


def _contract_source_lines(contract_path: Path) -> list[int]:
    path = Path(contract_path)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    lines: list[int] = []
    for contract in payload.get("contracts") or []:
        for line in contract.get("source_lines") or []:
            try:
                lines.append(int(line))
            except (TypeError, ValueError):
                continue
    return sorted(set(lines))


def _scene_class_ranges(code_path: Path) -> list[tuple[str, int, int]]:
    tree = ast.parse(Path(code_path).read_text(encoding="utf-8", errors="replace"))
    ranges: list[tuple[str, int, int]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name == "BaseConfigScene" or not _has_construct(node) or not _looks_like_scene_class(node):
            continue
        ranges.append((node.name, int(node.lineno), int(getattr(node, "end_lineno", node.lineno))))
    return ranges


def _has_construct(node: ast.ClassDef) -> bool:
    return any(isinstance(item, ast.FunctionDef) and item.name == "construct" for item in node.body)


def _looks_like_scene_class(node: ast.ClassDef) -> bool:
    if node.name == "Solution" or node.name.startswith("Scene_"):
        return True
    base_names = {_base_name(base) for base in node.bases}
    return any(name.endswith("Scene") or name == "BaseConfigScene" for name in base_names if name)


def _base_name(base: ast.expr) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Subscript):
        return _base_name(base.value)
    return ""


def _default_manim_command(candidate: Path, scenes: Sequence[str], *, quality: str, media_dir: Path) -> list[str]:
    command = [
        "manim",
        f"-q{quality}",
        "--disable_caching",
        "--media_dir",
        str(media_dir),
        str(candidate),
    ]
    command.extend(scenes)
    return command


def _short_media_dir(case_dir: Path) -> Path:
    digest = hashlib.sha1(str(case_dir.resolve()).encode("utf-8", errors="replace")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / "logic_engine_render_media" / digest


def _render_env(candidate: Path) -> dict[str, str]:
    env = dict(os.environ)
    shim_root = _ensure_tts_shim_dir()
    assets_dir = _ensure_smoke_assets_dir(candidate)
    extra_paths = [str(shim_root)]
    render_app = _repo_root() / "apps" / "render" / "app"
    if render_app.exists():
        extra_paths.append(str(render_app))
    existing = env.get("PYTHONPATH")
    if existing:
        extra_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(extra_paths)
    env["MATHPI_RENDER_ASSETS_DIR"] = str(assets_dir)
    env.setdefault("COSYVOICE_ALLOW_TTS_FALLBACK", "1")
    env.setdefault("COSYVOICE_DISABLE_WORD_TIMESTAMPS", "1")
    return env


def _ensure_tts_shim_dir() -> Path:
    root = Path(tempfile.gettempdir()) / "logic_engine_render_shims"
    package = root / "custom_services"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(
        "from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (package / "system_tts_service.py").write_text(_SYSTEM_TTS_SERVICE_SHIM, encoding="utf-8")
    return root


def _ensure_smoke_assets_dir(candidate: Path) -> Path:
    root = Path(tempfile.gettempdir()) / "logic_engine_render_assets"
    root.mkdir(parents=True, exist_ok=True)
    for rel_path in _enterprise_asset_paths(candidate):
        if _unsafe_asset_path(rel_path):
            continue
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_ONE_PIXEL_PNG)
    return root


def _enterprise_asset_paths(candidate: Path) -> list[Path]:
    try:
        tree = ast.parse(Path(candidate).read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    paths: list[Path] = []
    wanted = {"ENTERPRISE_BACKGROUND_ASSET", "ENTERPRISE_LOGO_ASSET"}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if not names.intersection(wanted):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            paths.append(Path(node.value.value))
    return paths


def _unsafe_asset_path(path: Path) -> bool:
    return path.is_absolute() or ".." in path.parts or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tail(text: str, *, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _decode_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


_SYSTEM_TTS_SERVICE_SHIM = r'''
from __future__ import annotations

import subprocess
from pathlib import Path

from manim_voiceover.services.base import SpeechService


class SilentSystemTTSService(SpeechService):
    def generate_from_text(self, text: str, cache_dir: str | None = None, path: str | None = None, **kwargs):
        if cache_dir is None:
            cache_dir = self.cache_dir
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        input_data = {"input_text": text, "service": "logic_engine_silent_system_tts"}
        audio_path = path or self.get_audio_basename(input_data) + ".mp3"
        full_path = Path(cache_dir) / audio_path
        _write_silent_mp3(full_path)
        return {
            "input_text": text,
            "input_data": input_data,
            "original_audio": audio_path,
        }


def create_system_tts_service(*args, **kwargs):
    return SilentSystemTTSService()


def _write_silent_mp3(path: Path, duration: float = 1.0) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        str(duration),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=10, check=False)
        if completed.returncode == 0 and path.exists() and path.stat().st_size > 0:
            return
    except Exception:
        pass
    silent_frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
    path.write_bytes(silent_frame * 5)
'''


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x04\x00\x00\x00"
    b"\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdac\xfc\xff\x1f"
    b"\x00\x03\x03\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)
