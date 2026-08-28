from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AssuranceInput:
    key: str
    question: str
    video_path: Path
    log_dir: Path
    solution_steps: str = ""
    final_answer: str = ""
    parsed_standard_answer: str = ""
    reviewer_supplemental_notes: dict[str, str] | None = None
    source_path: Path | None = None
    subtitle_path: Path | None = None
    original_image_path: Path | None = None
    preview_video_path: Path | None = None
    delivery_revision_id: str | None = None
    expected_video_sha256: str | None = None
    expected_source_sha256: str | None = None
    render_manifest_path: Path | None = None
    expected_render_manifest_sha256: str | None = None
    tts_mode: str = "required"


# Compatibility name for production callers. Labels deliberately do not live here.
AssuranceCase = AssuranceInput


class AssuranceLabel(StrEnum):
    GOOD = "GOOD"
    BAD = "BAD"
    UNLABELED = "UNLABELED"


@dataclass(frozen=True, slots=True)
class LabeledAssuranceCase:
    assurance_input: AssuranceInput
    label: AssuranceLabel
    human_tags: tuple[str, ...] = ()
    expected_verdict: str = ""

    def __getattr__(self, name: str):
        return getattr(self.assurance_input, name)


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
