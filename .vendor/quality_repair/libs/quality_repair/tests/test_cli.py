import json
from pathlib import Path

from libs.quality_repair.cli import _bundle_from_dir


def test_bundle_from_dir_uses_default_optional_paths_once(tmp_path: Path) -> None:
    (tmp_path / "candidate.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "layout_context.json").write_text(json.dumps({"status": "layout_failed"}), encoding="utf-8")
    (tmp_path / "bundle.json").write_text(json.dumps({"job_id": "case-1"}), encoding="utf-8")

    bundle = _bundle_from_dir(tmp_path)

    assert bundle.code_path == tmp_path / "candidate.py"
    assert bundle.layout_context == tmp_path / "layout_context.json"
