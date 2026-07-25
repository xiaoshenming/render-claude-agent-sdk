import json
from pathlib import Path

import pytest

from manim_quality.logic.eval_manifest import (
    EvalManifestError,
    load_frozen_eval_manifest,
)
from manim_quality.revisions.fingerprint import sha256_bytes


def artifact(root: Path, name: str, content: bytes) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"path": name, "sha256": sha256_bytes(content)}


def write_manifest(tmp_path: Path) -> Path:
    source = artifact(tmp_path, "pack/manifest.json", b"{}")
    candidate = artifact(tmp_path, "pack/samples/case/candidate.py", b"pass\n")
    data = {
        "schema_version": "manim-quality.logic-eval.v1",
        "pack_id": "pack-1",
        "truth": "known_good",
        "frozen": True,
        "dataset_root_env": "MANIM_LOGIC_EVAL_PACKS_ROOT",
        "source_manifest": source,
        "sample_count": 1,
        "samples": [
            {
                "sample_id": "case-1",
                "truth": "known_good",
                "artifacts": {"candidate.py": candidate},
            }
        ],
    }
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loader_verifies_every_frozen_artifact(tmp_path: Path) -> None:
    manifest = load_frozen_eval_manifest(
        write_manifest(tmp_path), dataset_root=tmp_path
    )

    assert manifest.pack_id == "pack-1"
    assert manifest.cases[0].sample_id == "case-1"


def test_loader_rejects_tampered_artifact(tmp_path: Path) -> None:
    path = write_manifest(tmp_path)
    (tmp_path / "pack/samples/case/candidate.py").write_text(
        "changed\n", encoding="utf-8"
    )

    with pytest.raises(EvalManifestError, match="hash mismatch"):
        load_frozen_eval_manifest(path, dataset_root=tmp_path)


def test_loader_rejects_sample_id_path_escape(tmp_path: Path) -> None:
    path = write_manifest(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["samples"][0]["sample_id"] = "../outside"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(EvalManifestError, match="sample_id"):
        load_frozen_eval_manifest(path, dataset_root=tmp_path)
