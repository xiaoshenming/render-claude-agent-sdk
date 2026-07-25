import json

import anyio
import pytest

from manim_quality.operator.models import ValidationOutcome
from manim_quality.operator.session import QualitySession
from manim_quality.operator.toolset import build_quality_tools

PROBLEM = "Prove that the two constructed lines are parallel."
CODE = f'''"""{PROBLEM}"""
from manim import *

class Solution(BaseConfigScene):
    def construct(self):
        line = Line(LEFT, RIGHT)
        self.add(line)
'''


class RelationStub:
    def __init__(self) -> None:
        self.calls = []

    async def check(self, request):
        self.calls.append(request)
        return {"holds": True, "residual": 0.0}


class LayoutStub:
    def __init__(self) -> None:
        self.revisions = []

    async def inspect(self, revision, problem_hash):
        self.revisions.append(revision.revision_id)
        return {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "blocking_count": 1 if revision.revision_id == "R0" else 0,
            "issues": (
                [{"issue_id": "overlap-1", "kind": "overlap"}]
                if revision.revision_id == "R0"
                else []
            ),
        }


class ValidatorStub:
    def __init__(self) -> None:
        self.revisions = []

    async def validate(self, revision, findings, problem_hash):
        self.revisions.append(revision.revision_id)
        return ValidationOutcome(
            passed=True,
            improved=True,
            summary="compile and directed checks passed",
            details={"blocking_count": 0},
            revision_id=revision.revision_id,
            code_hash=revision.code_hash,
            problem_hash=problem_hash,
        )


def tool_fixture():
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    relation = RelationStub()
    layout = LayoutStub()
    validator = ValidatorStub()
    tools = build_quality_tools(
        session=session,
        relation_checker=relation,
        layout_inspector=layout,
        revision_validator=validator,
    )
    return session, relation, layout, validator, {
        tool.name: tool for tool in tools
    }


def execute(tool, arguments):
    return json.loads(anyio.run(tool.execute, arguments).text)


def prime_tools(tools, revision_id: str = "R0") -> None:
    execute(tools["read_solution"], {"revision_id": revision_id})


def test_toolset_exposes_exact_seven_mcp_capabilities() -> None:
    *_items, tools = tool_fixture()

    assert tuple(tools) == (
        "read_solution",
        "check_relation",
        "record_findings",
        "apply_patch",
        "inspect_layout",
        "validate_revision",
        "submit_revision",
    )


def test_read_solution_returns_only_exact_solution_class() -> None:
    session, *_items, tools = tool_fixture()

    candidate = execute(tools["read_solution"], {"revision_id": "R0"})

    assert candidate["revision_id"] == "R0"
    assert candidate["code_hash"] == session.baseline.code_hash
    assert candidate["start_line"] == 4
    assert candidate["source"].startswith("class Solution(BaseConfigScene):")
    assert "from manim import" not in candidate["source"]
    assert PROBLEM not in candidate["source"]


def test_relation_and_layout_tools_delegate_without_model_paths() -> None:
    _session, relation, layout, _validator, tools = tool_fixture()

    relation_result = execute(
        tools["check_relation"],
        {
            "relation": "parallel",
            "operands": [[1, 0], [2, 0]],
            "expected": True,
        },
    )
    layout_result = execute(
        tools["inspect_layout"],
        {"revision_id": "R0"},
    )

    assert relation_result["holds"] is True
    assert relation.calls[0]["relation"] == "parallel"
    assert layout_result["blocking_count"] == 1
    assert layout.revisions == ["R0"]


def test_findings_patch_validation_and_submission_return_bound_receipts() -> None:
    session, _relation, _layout, validator, tools = tool_fixture()
    prime_tools(tools)
    execute(
        tools["record_findings"],
        {
            "findings": [
                {
                    "finding_id": "logic-1",
                    "category": "logic",
                    "severity": "blocking",
                    "summary": "The line relation is incorrect.",
                    "acceptance_criteria": "Directed relation check passes.",
                }
            ]
        },
    )
    receipt = execute(
        tools["apply_patch"],
        {
            "base_revision_id": "R0",
            "base_code_hash": session.baseline.code_hash,
            "scope": "logic",
            "old_text": "Line(LEFT, RIGHT)",
            "new_text": "Line(LEFT, 2 * RIGHT)",
            "finding_ids": ["logic-1"],
        },
    )

    assert receipt["base_revision_id"] == "R0"
    assert receipt["parent_code_hash"] == session.baseline.code_hash
    assert receipt["new_revision_id"] == "R1"
    assert receipt["new_code_hash"] == session.current_revision.code_hash
    assert receipt["patch_hash"] == session.current_revision.patch_hash
    assert receipt["effect"] == "revision_mutation"

    validation = execute(
        tools["validate_revision"],
        {"revision_id": "R1"},
    )
    execute(
        tools["inspect_layout"],
        {"revision_id": "R1"},
    )
    submitted = execute(
        tools["submit_revision"],
        {"revision_id": "R1"},
    )

    assert validation["passed"] is True
    assert validation["fingerprint"].startswith("sha256:")
    assert validator.revisions == ["R1"]
    assert submitted["submitted_revision_id"] == "R1"
    assert submitted["code_hash"] == session.current_revision.code_hash


def test_record_findings_schema_declares_the_runtime_item_contract() -> None:
    session, _relation, _layout, _validator, tools = tool_fixture()
    del session
    schema = tools["record_findings"].input_schema
    item = schema["properties"]["findings"]["items"]

    assert item["required"] == (
        "finding_id",
        "category",
        "severity",
        "summary",
        "acceptance_criteria",
    )
    assert item["additionalProperties"] is False
    assert item["properties"]["category"]["enum"] == ("logic", "layout")
    assert item["properties"]["severity"]["enum"] == ("blocking", "warning")


def test_patch_rejects_stale_revision_identity() -> None:
    session, *_items, tools = tool_fixture()
    prime_tools(tools)
    execute(
        tools["record_findings"],
        {
            "findings": [
                {
                    "finding_id": "logic-1",
                    "category": "logic",
                    "severity": "blocking",
                    "summary": "Wrong relation.",
                    "acceptance_criteria": "Relation passes.",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="base code hash"):
        execute(
            tools["apply_patch"],
            {
                "base_revision_id": "R0",
                "base_code_hash": "sha256:" + "0" * 64,
                "scope": "logic",
                "old_text": "Line(LEFT, RIGHT)",
                "new_text": "Line(LEFT, UP)",
                "finding_ids": ["logic-1"],
            },
        )

    assert session.current_revision.revision_id == "R0"


def test_layout_tool_rejects_stale_evidence_identity() -> None:
    class StaleLayout(LayoutStub):
        async def inspect(self, revision, problem_hash):
            report = await super().inspect(revision, problem_hash)
            report["revision_id"] = "OTHER"
            return report

    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    tools = build_quality_tools(
        session=session,
        relation_checker=RelationStub(),
        layout_inspector=StaleLayout(),
        revision_validator=ValidatorStub(),
    )
    by_name = {tool.name: tool for tool in tools}

    with pytest.raises(ValueError, match="stale evidence"):
        execute(by_name["inspect_layout"], {"revision_id": "R0"})


def test_findings_contract_rejects_malformed_nested_item() -> None:
    *_items, tools = tool_fixture()

    with pytest.raises(ValueError, match="finding"):
        execute(
            tools["record_findings"],
            {"findings": [{"finding_id": "missing-fields"}]},
        )
