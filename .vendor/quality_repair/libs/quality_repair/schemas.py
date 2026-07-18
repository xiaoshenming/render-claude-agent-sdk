"""quality_repair.schemas — 模块内共享数据结构。

所有层只依赖本文件与 interfaces.py / statuses.py，不互相 import 实现。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

PROFILE_LAYOUT = "layout"
PROFILE_LOGIC = "logic"
PROFILE_PRE_RENDER = "pre_render"  # 预留
ALL_PROFILES = (PROFILE_LAYOUT, PROFILE_LOGIC, PROFILE_PRE_RENDER)

REPAIRABILITY_AUTO_READY = "auto_ready"
REPAIRABILITY_DETECT_ONLY = "detect_only"
REPAIRABILITY_UNKNOWN = "unknown"


@dataclass(kw_only=True)
class Budget:
    """止损预算。上限是保险丝，真正止损靠进展驱动循环。"""

    max_rounds: int = 3
    token_hard_cap: int = 60_000
    no_progress_stop: int = 2       # 连续 N 轮无进展即停
    same_signature_stop: int = 3    # 同一失败签名第 N 次出现即停
    model: str | None = None        # None = 由 ClaudeSDKRunner 运行时配置决定
    accept_degraded_max_blocking: int | None = None
    accept_degraded_min_reduction_ratio: float = 0.5
    accept_risk_only_max_blocking: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_rounds": self.max_rounds,
            "token_hard_cap": self.token_hard_cap,
            "no_progress_stop": self.no_progress_stop,
            "same_signature_stop": self.same_signature_stop,
            "model": self.model,
            "accept_degraded_max_blocking": self.accept_degraded_max_blocking,
            "accept_degraded_min_reduction_ratio": self.accept_degraded_min_reduction_ratio,
            "accept_risk_only_max_blocking": self.accept_risk_only_max_blocking,
        }


def budget_for(profile: str, blocking_count: int) -> Budget:
    """设计方案 §七 的分级预算（实测数据校准）。"""
    if profile == PROFILE_LOGIC:
        return Budget(max_rounds=2, token_hard_cap=40_000)
    if profile == PROFILE_LAYOUT:
        return Budget(
            max_rounds=2,
            token_hard_cap=60_000,
            no_progress_stop=1,
            same_signature_stop=2,
            accept_degraded_max_blocking=2,
            accept_degraded_min_reduction_ratio=0.5,
            accept_risk_only_max_blocking=6,
        )
    return Budget(max_rounds=2, token_hard_cap=60_000)


@dataclass(kw_only=True)
class CheckResult:
    """外层确定性 checker 的结构化结果 —— 唯一裁判。"""

    ok: bool                      # checker 本身是否成功运行
    passed: bool                  # 是否无 blocking 问题
    blocking_count: int
    issues: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def signature(self) -> str:
        """稳定失败签名：用于同签名 N 次即停。"""
        key = json.dumps(
            sorted(
                (
                    str(i.get("kind", i.get("type", ""))),
                    str(i.get("a", i.get("object_a", ""))),
                    str(i.get("b", i.get("object_b", ""))),
                )
                for i in self.issues
            ),
            ensure_ascii=False,
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "passed": self.passed,
            "blocking_count": self.blocking_count,
            "issues": list(self.issues),
            "error": self.error,
            "signature": self.signature,
        }

    @classmethod
    def failure(cls, error: str) -> "CheckResult":
        return cls(ok=False, passed=False, blocking_count=-1, error=error)


@dataclass(kw_only=True)
class AgentRunReport:
    """执行器一轮运行的结果（executor 自述，不作验收依据）。"""

    changed: bool
    tokens_used: int = 0
    cost_usd: float = 0.0
    transcript_path: Path | None = None
    tool_calls: dict[str, int] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    final_text: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "transcript_path": str(self.transcript_path) if self.transcript_path else None,
            "tool_calls": dict(self.tool_calls),
            "usage": dict(self.usage),
            "final_text": self.final_text,
            "error": self.error,
        }


@dataclass(kw_only=True)
class AcceptanceReport:
    """验收层输出：六态 + 各门禁明细。status 可为内部态 REPAIR_WORSE。"""

    status: str
    gates: dict[str, str] = field(default_factory=dict)  # gate 名 -> pass/fail/skip/error
    reasons: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "gates": dict(self.gates),
            "reasons": list(self.reasons),
            "before": dict(self.before),
            "after": dict(self.after),
        }


@dataclass(kw_only=True)
class RepairabilityDecision:
    """路由分类层输出。"""

    classification: str           # auto_ready | detect_only | unknown
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"classification": self.classification, "reasons": list(self.reasons)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
