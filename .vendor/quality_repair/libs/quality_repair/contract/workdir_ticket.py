"""Ticket writer for repair workdirs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..schemas import PROFILE_LOGIC
from .workdir_format import _format_issue
from .workdir_normalize import COLLISION_KEYS, LOGIC_ISSUE_KEYS, _find_list_field


def _write_ticket(
    dest: Path,
    bundle: Any,
    layout_ctx: dict[str, Any] | None,
    logic_contract: dict[str, Any] | None,
) -> None:
    if bundle.profile == PROFILE_LOGIC:
        issues = _find_list_field(logic_contract, LOGIC_ISSUE_KEYS)
        goal = "按 source_line / repair_hint 做最小编辑集，可多次 Edit，清零合同阻断"
    else:
        issues = _find_list_field(layout_ctx, COLLISION_KEYS)
        goal = "blocking 归零且不得新增出界/新碰撞"
    lines = [
        "# 修复工单",
        "",
        f"- profile: {bundle.profile}",
        f"- job_id: {bundle.job_id}",
        f"- 问题条数: {len(issues)}",
        "",
        "## 问题清单",
    ]
    lines.extend(f"- {_format_issue(issue)}" for issue in issues)
    if not issues:
        lines.append("- (未解析到结构化问题条目，若非预期请查 build_warnings.json)")
    lines += [
        "",
        "## 修复目标",
        f"- {goal}",
        "",
        "## 禁改区声明",
        "- 详见 facts/protected.json：禁止修改 Header ABI 函数"
        "（set_speech_service/GlobalConfig/show_text/setup_layout）、"
        "MathTex/Tex 字符串字面量、set_color 调用。",
        "",
        "## 执行约束",
        "- 只允许编辑 candidate.py。",
    ]
    (dest / "TICKET.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
