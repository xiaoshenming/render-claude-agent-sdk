from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect
from manim_quality.agents.profile import operator_profile
from manim_quality.operator import request_builder
from manim_quality.operator.tool_schemas import CHECK_RELATION_SCHEMA


class _Session:
    current_revision = type("Revision", (), {"revision_id": "R0"})()

    def mark_solution_read(self, _revision_id):
        return None


async def _handler(_arguments):
    return {"content": [{"type": "text", "text": "ok"}]}


def _grant(name):
    return ManagedToolGrant(
        server_name="quality",
        name=name,
        description="test tool",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=_handler,
        effect=ToolEffect.READ_ONLY,
        max_calls=1,
        timeout_ms=1_000,
        max_result_chars=1_000,
    )


def test_check_relation_declares_all_supported_operand_shapes():
    items = CHECK_RELATION_SCHEMA["properties"]["operands"]["items"]

    assert items == {
        "oneOf": [
            {"type": "number"},
            {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 3,
            },
        ]
    }


def test_glm_operator_keeps_check_relation(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text("class Solution: pass\n", encoding="utf-8")
    monkeypatch.setattr(
        request_builder,
        "build_quality_tools",
        lambda **_kwargs: (_grant("check_relation"), _grant("inspect_layout")),
    )

    request = request_builder.operator_request(
        run_id="run-1",
        model="glm-5.3-flash",
        profile=operator_profile(model="glm-5.3-flash", prompt_version="test"),
        prompt="test",
        workspace=tmp_path,
        candidate_path=candidate,
        session=_Session(),
        relation_checker=object(),
        layout_inspector=object(),
        revision_validator=object(),
        context_bytes=1,
        output_validator=None,
        estimated_input_tokens=1,
        reserved_output_tokens=1,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )

    assert [tool.name for tool in request.managed_tools] == [
        "check_relation",
        "inspect_layout",
    ]
