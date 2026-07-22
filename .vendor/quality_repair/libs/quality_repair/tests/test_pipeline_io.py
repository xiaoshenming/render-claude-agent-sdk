from __future__ import annotations

import json
from pathlib import Path

from libs.quality_repair.pipeline_io import prompt_for, refresh_layout_context_from_check
from libs.quality_repair.schemas import CheckResult


def test_layout_prompt_uses_audit_direct_protocol_without_ticket_dump(tmp_path: Path) -> None:
    (tmp_path / "candidate.py").write_text("class Scene_06_Test:\n    pass\n", encoding="utf-8")
    (tmp_path / "layout_context.json").write_text(
        json.dumps(
            {
                "blocking_layout_issue_count": 2,
                "top_blocking_issues": [{"a": "A", "b": "B"}, {"a": "C", "b": "D"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "TICKET.md").write_text(
        "# 修复工单\n\n## 问题清单\n- overlap: A vs B\n- overlap: C vs D\n",
        encoding="utf-8",
    )

    prompt = prompt_for("layout", tmp_path)

    assert "diagnostic-and-repair agent" not in prompt
    assert "Manim layout repair agent" in prompt
    assert "Scene:\n- Scene_06_Test" in prompt
    assert "Round:\n- 1" in prompt
    assert "Current blocking overlap count:\n- 2" in prompt
    assert f"Read {tmp_path / 'layout_issue_digest.json'} first" in prompt
    assert "candidate_anchor_windows.md" not in prompt
    assert f"Read {tmp_path / 'candidate.py'} once" in prompt
    assert f"edit {tmp_path / 'candidate.py'} for the clearly source-fixable layout clusters" in prompt
    assert "Use short exact Edit.old_string snippets" in prompt
    assert "Group the digest by shared source object, parent VGroup, or layout statement" in prompt
    assert "Do not stop after the first improvement" in prompt
    assert "every remaining clearly source-fixable blocking cluster" in prompt
    assert "after a strong improvement, stop" not in prompt
    assert "smallest related layout change" not in prompt
    assert "Never read full candidate.py" not in prompt
    assert f"Do not read any file except {tmp_path / 'layout_issue_digest.json'} and {tmp_path / 'candidate.py'}" in prompt
    assert "layout_repair_brief.json" not in prompt
    assert "layout_repair_contract.json" not in prompt
    assert "/workspace/layout_repair_brief.json" not in prompt
    assert "Do not write analysis, markdown, code fences, or prose" in prompt
    assert "Preserve MathTex/Text strings, voiceover text" in prompt
    assert "need_more_evidence" not in prompt
    assert "evidence_requests" not in prompt
    assert "risk_hints" not in prompt
    assert "issue groups" not in prompt
    assert "generic no_fix" in prompt
    assert "Final JSON shape" in prompt
    assert "After editing or deciding not to edit" not in prompt
    assert "Do not chase low-confidence or risk-only residual issues" in prompt
    assert "Read TICKET.md first" not in prompt
    assert "layout_context.json" not in prompt
    assert "## 问题清单" not in prompt
    assert "布局修复任务" not in prompt


def test_non_layout_prompt_keeps_ticket_context(tmp_path: Path) -> None:
    (tmp_path / "TICKET.md").write_text("logic ticket body\n", encoding="utf-8")

    prompt = prompt_for("logic", tmp_path)

    assert "逻辑修复任务" in prompt
    assert "logic ticket body" in prompt
    assert "logic_contract_context.json" in prompt
    assert "source_region.md" in prompt
    assert "suggested_replacement" in prompt
    assert "先读 `source_region.md`" in prompt
    assert "禁止整文件读取 `candidate.py`" in prompt
    assert "可以做多次 `Edit`" in prompt
    assert "最多读取 3 个 `candidate.py` 局部片段" in prompt
    assert "原错误 `claim_text` 不再出现在源码中" in prompt
    assert "Use exact raw lines as Edit.old_string context" in prompt


def test_layout_prompt_uses_construct_class_when_scene_prefix_absent(tmp_path: Path) -> None:
    (tmp_path / "candidate.py").write_text(
        "class GlobalConfig:\n"
        "    pass\n\n"
        "class BaseConfigScene:\n"
        "    pass\n\n"
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "layout_context.json").write_text(
        json.dumps({"blocking_layout_issue_count": 1}),
        encoding="utf-8",
    )

    prompt = prompt_for("layout", tmp_path)

    assert "Scene:\n- Solution" in prompt


def test_layout_prompt_targets_core_candidate_when_view_is_enabled(tmp_path: Path) -> None:
    (tmp_path / "candidate.py").write_text(
        "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n",
        encoding="utf-8",
    )
    (tmp_path / "candidate_prelude.txt").write_text("from manim import *\n\n", encoding="utf-8")
    (tmp_path / "core_candidate.py").write_text("class Solution(Scene):\n    def construct(self):\n        self.wait()\n", encoding="utf-8")
    (tmp_path / "candidate_core_map.json").write_text('{"enabled":true,"scene_class":"Solution","core_start_line":3}', encoding="utf-8")
    (tmp_path / "layout_context.json").write_text(json.dumps({"blocking_layout_issue_count": 3}), encoding="utf-8")

    prompt = prompt_for("layout", tmp_path)

    assert f"Read {tmp_path / 'core_candidate.py'} once" in prompt
    assert f"Edit only {tmp_path / 'core_candidate.py'}" in prompt
    assert str(tmp_path / "layout_issue_digest.json") in prompt
    assert "Do not read candidate.py or candidate_prelude.txt" in prompt
    assert "The full candidate.py will be composed and checked automatically" in prompt
    assert f"Do not read any file except {tmp_path / 'layout_issue_digest.json'} and {tmp_path / 'core_candidate.py'}" in prompt
    assert "Do not use /workspace paths" in prompt


def test_refresh_layout_context_from_check_refreshes_digest_without_anchor_windows(tmp_path: Path) -> None:
    (tmp_path / "candidate.py").write_text(
        "class Scene_Anchor:\n"
        "    def make_problem_panel(self):\n"
        "        problem_panel = VGroup(MathTex(\"35^\\\\circ\"), Text('题目'))\n"
        "        return problem_panel\n"
        "\n"
        "    def construct(self):\n"
        "        step_panel = self.make_problem_panel()\n"
        "        self.add(step_panel)\n"
        + "\n".join(f"    filler_{index} = {index}" for index in range(80))
        + "\n    unrelated_tail_marker = 'do not include the whole candidate'\n",
        encoding="utf-8",
    )
    (tmp_path / "layout_context.json").write_text(json.dumps({"blocking_layout_issue_count": 0}), encoding="utf-8")
    check = CheckResult(
        ok=True,
        passed=False,
        blocking_count=1,
        issues=[
            {
                "category": "text_formula_overlap",
                "a": {"name": "problem_panel", "class": "MathTex", "kind": "formula", "text": "35°"},
                "b": {"name": "step_panel", "class": "Text", "kind": "text", "text": "步骤 1"},
            }
        ],
    )

    refresh_layout_context_from_check(tmp_path, check)

    digest = json.loads((tmp_path / "layout_issue_digest.json").read_text(encoding="utf-8"))
    assert digest["schema_version"] == "quality_repair.layout_issue_digest.issue_only.v1"
    assert digest["issue_count"] == 1
    assert digest["issues"][0]["category"] == "text_formula_overlap"
    assert not (tmp_path / "agent_safety_contract.json").exists()
    assert not (tmp_path / "candidate_anchor_windows.md").exists()
