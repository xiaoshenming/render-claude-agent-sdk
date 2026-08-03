from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import AssuranceInput


@dataclass(frozen=True, slots=True)
class ArtifactIdentityReceipt:
    revision_id: str | None
    source_sha256: str | None
    video_sha256: str | None
    render_manifest_sha256: str | None
    risk_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_artifact_identity(case: AssuranceInput) -> ArtifactIdentityReceipt:
    actual = ArtifactIdentityReceipt(
        revision_id=_observed_revision(case),
        source_sha256=_file_sha(case.source_path),
        video_sha256=_file_sha(case.video_path),
        render_manifest_sha256=_file_sha(case.render_manifest_path),
        risk_codes=(),
    )
    risks = tuple(
        code
        for expected, observed, code in (
            (
                case.delivery_revision_id,
                actual.revision_id,
                "revision_identity_mismatch",
            ),
            (case.expected_source_sha256, actual.source_sha256, "source_sha_mismatch"),
            (case.expected_video_sha256, actual.video_sha256, "video_sha_mismatch"),
            (
                case.expected_render_manifest_sha256,
                actual.render_manifest_sha256,
                "render_manifest_sha_mismatch",
            ),
        )
        if expected is not None and expected != observed
    )
    return ArtifactIdentityReceipt(
        revision_id=actual.revision_id,
        source_sha256=actual.source_sha256,
        video_sha256=actual.video_sha256,
        render_manifest_sha256=actual.render_manifest_sha256,
        risk_codes=risks,
    )


def _observed_revision(case: AssuranceInput) -> str | None:
    path = case.log_dir / "run_summary.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    revision = value.get("final_revision_id") if isinstance(value, dict) else None
    return str(revision) if revision else None


def _file_sha(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
