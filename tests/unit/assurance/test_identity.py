import hashlib
import json

from manim_quality.assurance.identity import inspect_artifact_identity
from manim_quality.assurance.models import AssuranceInput


def test_identity_receipt_checks_revision_source_video_and_manifest(tmp_path) -> None:
    source = tmp_path / "main.py"
    video = tmp_path / "final.mp4"
    manifest = tmp_path / "render.json"
    logs = tmp_path / "logs"
    logs.mkdir()
    source.write_text("print('ok')\n", encoding="utf-8")
    video.write_bytes(b"video")
    manifest.write_text("{}\n", encoding="utf-8")
    (logs / "run_summary.json").write_text(
        json.dumps({"final_revision_id": "R2"}), encoding="utf-8"
    )
    case = AssuranceInput(
        key="case",
        question="q",
        video_path=video,
        source_path=source,
        log_dir=logs,
        render_manifest_path=manifest,
        delivery_revision_id="R3",
        expected_source_sha256="bad",
        expected_video_sha256=_sha(video),
        expected_render_manifest_sha256=_sha(manifest),
    )

    receipt = inspect_artifact_identity(case)

    assert receipt.risk_codes == (
        "revision_identity_mismatch",
        "source_sha_mismatch",
    )
    assert receipt.video_sha256 == _sha(video)


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
