"""Claude Agent SDK adapters for logic review and scene patch planning."""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.workers.post_render_logic.scene_patch import apply_scene_replacements
from app.workers.post_render_logic.schemas import (
    LogicEvidence,
    LogicIssue,
    RepairPlan,
    ReviewReport,
)


class JsonRunner(Protocol):
    async def run_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str,
    ) -> dict[str, Any]: ...


class ClaudeLogicReviewer:
    """Reviewer adapter: SDK JSON -> ReviewReport."""

    def __init__(self, runner: JsonRunner) -> None:
        self.runner = runner

    async def review(self, evidence: LogicEvidence) -> ReviewReport:
        payload = await self.runner.run_json(
            prompt=_review_prompt(evidence),
            schema=REVIEW_REPORT_SCHEMA,
            system_prompt=REVIEW_SYSTEM_PROMPT,
        )
        return _review_from_payload(payload, evidence.source_code_hash)


class ClaudeSceneCoder:
    """Coder adapter: SDK replacements -> safe scene patch."""

    def __init__(self, runner: JsonRunner) -> None:
        self.runner = runner

    async def patch(self, code: str, plan: RepairPlan):
        payload = await self.runner.run_json(
            prompt=_coder_prompt(code, plan),
            schema=CODER_REPLACEMENTS_SCHEMA,
            system_prompt=CODER_SYSTEM_PROMPT,
        )
        replacements = payload.get("replacements") or {}
        fixed_code, attempt = apply_scene_replacements(
            code=code,
            replacements=replacements,
            plan_id=plan.plan_id,
            issue_ids=plan.issue_ids,
        )
        attempt.risk_flags.extend(payload.get("risk_flags") or [])
        return fixed_code, attempt


REVIEW_SYSTEM_PROMPT = (
    "你是 Shuxuepai post-render 逻辑审查器。只审查已成功渲染代码中的"
    "文本、公式、题意和 Scene 逻辑一致性；不做视觉审查，不做布局重叠审查，"
    "不修代码。必须输出 JSON。只报告有直接文本/代码证据的问题。"
)

CODER_SYSTEM_PROMPT = (
    "你是 Shuxuepai post-render 逻辑修复 coder。只允许返回 replacements JSON，"
    "不能输出完整代码，不能修改 BaseConfigScene/header/helper，不能改无关 Scene，"
    "不能顺手优化。"
)


REVIEW_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["review_id", "decision", "blocked", "issues"],
    "properties": {
        "review_id": {"type": "string"},
        "decision": {
            "type": "string",
            "enum": ["pass", "repair", "record_only", "human_review"],
        },
        "blocked": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "issue_id",
                    "issue_type",
                    "severity",
                    "confidence",
                    "repairable",
                    "repair_scope",
                    "target_scene_ids",
                    "evidence",
                    "expected",
                    "observed",
                    "acceptance_predicates",
                    "non_goals",
                ],
                "properties": {
                    "issue_id": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "confidence": {"type": "number"},
                    "repairable": {"type": "boolean"},
                    "repair_scope": {"type": "string"},
                    "target_scene_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "expected": {"type": "string"},
                    "observed": {"type": "string"},
                    "acceptance_predicates": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "non_goals": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}

CODER_REPLACEMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["replacements", "risk_flags"],
    "properties": {
        "replacements": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
}


def _review_prompt(evidence: LogicEvidence) -> str:
    return (
        "请审查下面 evidence 中的 post-render 逻辑问题。"
        "只输出符合 schema 的 JSON，不要解释。\n\n"
        f"{json.dumps(evidence.to_dict(), ensure_ascii=False)}"
    )


def _coder_prompt(code: str, plan: RepairPlan) -> str:
    return (
        "请根据 repair_plan 生成最小 replacements。"
        "replacements 的 key 是目标 Scene 名，value 是 {原字符串: 新字符串}。"
        "只替换 plan 允许范围内的文本/公式 claim。\n\n"
        "repair_plan:\n"
        f"{json.dumps(plan.to_dict(), ensure_ascii=False)}\n\n"
        "code:\n"
        f"{code}"
    )


def _review_from_payload(
    payload: dict[str, Any],
    source_code_hash: str,
) -> ReviewReport:
    issues = [
        LogicIssue(
            issue_id=str(item["issue_id"]),
            issue_type=str(item["issue_type"]),
            severity=item["severity"],
            confidence=float(item["confidence"]),
            repairable=bool(item["repairable"]),
            repair_scope=str(item["repair_scope"]),
            target_scene_ids=list(item["target_scene_ids"]),
            evidence=list(item["evidence"]),
            expected=str(item.get("expected") or ""),
            observed=str(item.get("observed") or ""),
            acceptance_predicates=list(item.get("acceptance_predicates") or []),
            non_goals=list(item.get("non_goals") or []),
        )
        for item in payload.get("issues") or []
    ]
    return ReviewReport(
        review_id=str(payload["review_id"]),
        source_code_hash=source_code_hash,
        decision=payload["decision"],
        issues=issues,
        blocked=bool(payload.get("blocked", False)),
    )
