from dataclasses import dataclass
from types import MappingProxyType

from manim_quality.agents._claude_hook_values import _json_safe


@dataclass(frozen=True)
class _UsageEnvelope:
    model_usage: object


def test_json_safe_handles_mappingproxy_nested_in_dataclass() -> None:
    value = _UsageEnvelope(
        MappingProxyType(
            {"gpt-5.6-sol": MappingProxyType({"inputTokens": 123})}
        )
    )

    assert _json_safe(value) == {
        "model_usage": {"gpt-5.6-sol": {"inputTokens": 123}}
    }
