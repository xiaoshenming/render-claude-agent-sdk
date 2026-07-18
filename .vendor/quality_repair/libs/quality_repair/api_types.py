"""Public dataclasses for the quality_repair API surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schemas import Budget, PROFILE_LAYOUT, REPAIRABILITY_UNKNOWN


@dataclass(kw_only=True)
class RepairBundle:
    job_id: str
    code_path: Path
    profile: str = PROFILE_LAYOUT       # layout | logic | pre_render(预留)
    candidate_mode: str = "core"         # core | full; layout profile only
    # --- layout profile ---
    layout_context: Path | None = None  # 结构化 bbox/碰撞清单 JSON
    # --- logic profile ---
    logic_contract: Path | None = None  # logic_contract_context.json
    source_region: Path | None = None   # source_region.md
    render_artifacts: Path | None = None
    frames: list[Path] = field(default_factory=list)
    budget: Budget | None = None        # None = 按 profile/blocking 分级
    evidence_root: Path | None = None   # None = code_path 同级 evidence/


@dataclass(kw_only=True)
class RepairResult:
    status: str                         # statuses.EXTERNAL_STATUSES 之一
    code_path: Path                     # UNCHANGED 时 == 输入
    repairability: str = REPAIRABILITY_UNKNOWN
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    rounds_used: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    evidence_dir: Path | None = None
    reasons: list[str] = field(default_factory=list)
