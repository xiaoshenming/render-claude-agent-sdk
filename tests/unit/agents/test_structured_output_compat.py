from manim_quality.agents._structured_output_compat import adapt_structured_output


def test_adapter_removes_provider_extras_and_bounds_strings() -> None:
    schema = {
        "properties": {
            "status": {"type": "string"},
            "summary": {"type": "string", "maxLength": 5},
        },
        "additionalProperties": False,
    }

    assert adapt_structured_output(
        {"status": "held", "summary": "123456", "provider_note": "x"}, schema
    ) == {"status": "held", "summary": "12345"}


def test_adapter_does_not_invent_missing_semantic_fields() -> None:
    schema = {"properties": {"status": {"type": "string"}}}

    assert adapt_structured_output({"summary": "only prose"}, schema) == {}
