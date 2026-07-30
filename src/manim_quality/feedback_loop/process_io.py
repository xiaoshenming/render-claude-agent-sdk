from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def copy_coder_evidence(source: Path, target: Path) -> None:
    run_root = source.parent.parent
    for relative in (
        "logs/run_summary.json",
        "evidence/findings.json",
        "output/decision.json",
    ):
        path = run_root / relative
        if path.is_file():
            shutil.copy2(path, target / path.name)


def run_command(argv: list[str], log_path: Path, cwd: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    source_root = str((cwd / "src").resolve())
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_root, environment.get("PYTHONPATH", "")) if item
    )
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            argv, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {log_path}")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
