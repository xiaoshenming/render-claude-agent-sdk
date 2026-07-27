from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AssuranceCase:
    key: str
    question: str
    human_tags: tuple[str, ...]
    expected_verdict: str
    video_path: Path
    log_dir: Path
    source_path: Path | None = None
    subtitle_path: Path | None = None
    original_image_path: Path | None = None
    preview_video_path: Path | None = None
    delivery_revision_id: str | None = None
    expected_video_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ToolReport:
    tool: str
    status: str
    risk_codes: tuple[str, ...]
    evidence: tuple[dict[str, object], ...]
    artifacts: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return self.status == "risk"

    def as_dict(self) -> dict[str, object]:
        return {
            "tool": self.tool,
            "status": self.status,
            "risk_codes": list(self.risk_codes),
            "evidence": list(self.evidence),
            "artifacts": list(self.artifacts),
        }
