import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio
import pytest

from manim_quality.operator.models import ValidationOutcome
from manim_quality.operator.session import QualitySession
from manim_quality.operator.session_errors import InvalidSessionTransition
from manim_quality.operator.toolset import build_quality_tools

PROBLEM = "Show why the line points right."
CODE = f'''"""{PROBLEM}"""
from manim import *

class Solution(BaseConfigScene):
    def construct(self):
        arrow = Arrow(LEFT, RIGHT)
        self.add(arrow)
'''


class Relation:
    async def check(self, request):
        return {"holds": request["expected"] is True}


class Layout:
    async def inspect(self, revision, problem_hash):
        return {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "blocking_count": 0,
            "issues": [],
        }


class Validator:
    async def validate(self, revision, findings, problem_hash):
        return ValidationOutcome(
            True,
            True,
            "passed",
            {"finding_count": len(findings)},
            revision.revision_id,
            revision.code_hash,
            problem_hash,
        )


def _execute(tool, arguments):
    return json.loads(anyio.run(tool.execute, arguments).text)


def _fixture(tmp_path: Path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(CODE, encoding="utf-8")
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    tools = build_quality_tools(
        session=session,
        relation_checker=Relation(),
        layout_inspector=Layout(),
        revision_validator=Validator(),
        candidate_path=candidate,
    )
    return session, candidate, {tool.name: tool for tool in tools}


def test_custom_read_and_edit_substitutes_are_removed(tmp_path: Path) -> None:
    _session, _candidate, tools = _fixture(tmp_path)

    assert set(tools) == {
        "check_relation",
        "record_findings",
        "recover_revision",
        "inspect_layout",
        "validate_revision",
        "submit_revision",
    }
    assert "read_solution" not in tools
    assert "apply_patch" not in tools


def test_native_file_edit_becomes_immutable_revision_on_validation(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    finding = {
        "finding_id": "logic-1",
        "category": "logic",
        "severity": "blocking",
        "summary": "Direction explanation is missing.",
        "acceptance_criteria": "Show and explain the rightward direction.",
    }
    _execute(tools["record_findings"], {"findings": [finding]})
    candidate.write_text(
        CODE.replace(
            "self.add(arrow)",
            'self.add(arrow, Text("right").next_to(arrow, UP))',
        ),
        encoding="utf-8",
    )

    receipt = _execute(
        tools["validate_revision"],
        {"revision_id": "R0", "finding_ids": ["logic-1"]},
    )

    assert receipt["revision_id"] == "R1"
    assert session.current_revision.revision_id == "R1"
    assert session.current_revision.parent_revision_id == "R0"
    assert session.current_revision.finding_ids == ("logic-1",)


def test_combined_native_edit_binds_logic_and_layout_findings(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    findings = [
        {
            "finding_id": "logic-1",
            "category": "logic",
            "severity": "blocking",
            "summary": "Direction explanation is missing.",
            "acceptance_criteria": "Explain the direction.",
        },
        {
            "finding_id": "layout-1",
            "category": "layout",
            "severity": "blocking",
            "summary": "Direction label overlaps the arrow.",
            "acceptance_criteria": "Move the label above the arrow.",
        },
    ]
    _execute(tools["record_findings"], {"findings": findings})
    candidate.write_text(
        CODE.replace(
            "self.add(arrow)",
            'self.add(arrow, Text("right").next_to(arrow, UP))',
        ),
        encoding="utf-8",
    )
    binding = {
        "revision_id": "R0",
        "finding_ids": ["logic-1", "layout-1"],
    }

    receipt = _execute(tools["validate_revision"], binding)
    _execute(tools["inspect_layout"], binding)
    submitted = _execute(
        tools["submit_revision"],
        {"revision_id": receipt["revision_id"]},
    )

    assert session.current_revision.finding_ids == ("logic-1", "layout-1")
    assert submitted["submitted_revision_id"] == "R1"


def test_submit_tool_has_retry_budget(tmp_path: Path) -> None:
    _session, _candidate, tools = _fixture(tmp_path)

    assert tools["submit_revision"].max_calls >= 4


def test_parallel_validation_and_layout_share_one_native_revision(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    finding = {
        "finding_id": "logic-1",
        "category": "logic",
        "severity": "blocking",
        "summary": "Direction explanation is missing.",
        "acceptance_criteria": "Show the direction label.",
    }
    _execute(tools["record_findings"], {"findings": [finding]})
    candidate.write_text(
        CODE.replace("self.add(arrow)", "self.add(arrow.shift(UP))"),
        encoding="utf-8",
    )

    async def run_both():
        return await asyncio.gather(
            tools["validate_revision"].execute(
                {"revision_id": "R0", "finding_ids": ["logic-1"]}
            ),
            tools["inspect_layout"].execute(
                {"revision_id": "R0", "finding_ids": ["logic-1"]}
            ),
        )

    validation, layout = anyio.run(run_both)

    assert json.loads(validation.text)["revision_id"] == "R1"
    assert json.loads(layout.text)["revision_id"] == "R1"
    assert len(session.attempts) == 2


def test_cross_thread_validation_and_layout_share_one_native_revision(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    finding = {
        "finding_id": "logic-1",
        "category": "logic",
        "severity": "blocking",
        "summary": "Direction explanation is missing.",
        "acceptance_criteria": "Show the direction label.",
    }
    _execute(tools["record_findings"], {"findings": [finding]})
    candidate.write_text(
        CODE.replace("self.add(arrow)", "self.add(arrow.shift(UP))"),
        encoding="utf-8",
    )
    binding = {"revision_id": "R0", "finding_ids": ["logic-1"]}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(_execute, tools["validate_revision"], binding),
            pool.submit(_execute, tools["inspect_layout"], binding),
        )
        validation, layout = (item.result() for item in futures)

    assert validation["revision_id"] == "R1"
    assert layout["revision_id"] == "R1"
    assert len(session.attempts) == 2


def test_recover_revision_restores_native_candidate_file(tmp_path: Path) -> None:
    session, candidate, tools = _fixture(tmp_path)
    finding = {
        "finding_id": "logic-1",
        "category": "logic",
        "severity": "blocking",
        "summary": "Direction explanation is missing.",
        "acceptance_criteria": "Show the direction label.",
    }
    _execute(tools["record_findings"], {"findings": [finding]})
    candidate.write_text(
        CODE.replace("self.add(arrow)", "self.add(arrow.shift(UP))"),
        encoding="utf-8",
    )
    _execute(
        tools["validate_revision"],
        {"revision_id": "R0", "finding_ids": ["logic-1"]},
    )

    receipt = _execute(tools["recover_revision"], {"revision_id": "R0"})

    assert receipt["revision_id"] == "R0"
    assert candidate.read_text(encoding="utf-8") == CODE
    assert session.current_revision.revision_id == "R0"


def test_recover_current_revision_overwrites_invalid_native_edit(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    candidate.write_text("this is not valid Python )", encoding="utf-8")

    receipt = _execute(tools["recover_revision"], {"revision_id": "R0"})

    assert receipt["revision_id"] == "R0"
    assert candidate.read_text(encoding="utf-8") == CODE
    assert session.current_revision.revision_id == "R0"


def test_recover_best_render_passed_falls_back_to_r0(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    candidate.write_text("this is not valid Python )", encoding="utf-8")

    receipt = _execute(
        tools["recover_revision"],
        {"revision_id": "best_render_passed"},
    )

    assert receipt["revision_id"] == "R0"
    assert candidate.read_text(encoding="utf-8") == CODE
    assert session.current_revision.revision_id == "R0"


def test_native_edit_requires_recorded_finding(tmp_path: Path) -> None:
    _session, candidate, tools = _fixture(tmp_path)
    candidate.write_text(
        CODE.replace("self.add(arrow)", "self.add(arrow.shift(UP))"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="addressed finding_ids"):
        _execute(
            tools["validate_revision"],
            {"revision_id": "R0", "finding_ids": []},
        )


def test_native_edit_may_submit_with_findings_retained_as_evidence(
    tmp_path: Path,
) -> None:
    session, candidate, tools = _fixture(tmp_path)
    findings = [
        {
            "finding_id": finding_id,
            "category": "logic",
            "severity": "blocking",
            "summary": summary,
            "acceptance_criteria": criteria,
        }
        for finding_id, summary, criteria in (
            ("logic-1", "Direction label is missing.", "Add the direction label."),
            ("logic-2", "Endpoint label is missing.", "Add the endpoint label."),
        )
    ]
    _execute(tools["record_findings"], {"findings": findings})
    candidate.write_text(
        CODE.replace("self.add(arrow)", "self.add(arrow.shift(UP))"),
        encoding="utf-8",
    )
    binding = {"revision_id": "R0", "finding_ids": ["logic-1"]}
    _execute(tools["validate_revision"], binding)
    _execute(tools["inspect_layout"], binding)

    result = _execute(tools["submit_revision"], {"revision_id": "R1"})
    assert result["status"] == "submitted"
    assert session.submitted_revision_id == "R1"
