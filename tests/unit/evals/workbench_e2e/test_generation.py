import json

import pytest
import requests

from evals.workbench_e2e.generation import (
    GenerationClient,
    GenerationConfig,
    GenerationFailed,
    extract_manim_code,
)


def test_extract_manim_code_accepts_fenced_or_plain_source():
    fenced = "before\n```python\nfrom manim import *\nclass Solution(Scene): pass\n```"
    plain = "from manim import *\nclass Solution(Scene): pass\n# === END ==="

    assert extract_manim_code(fenced).startswith("from manim")
    assert extract_manim_code(plain) == plain


def test_generation_client_records_usage_without_secret(tmp_path):
    seen = {}

    def transport(url, *, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return _Response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "from manim import *\n"
                            "class Solution(Scene): pass\n"
                            "# === END ==="
                        ),
                    }
                ],
                "usage": {"input_tokens": 120, "output_tokens": 80},
            }
        )

    config = GenerationConfig(
        base_url="https://example.invalid/v1",
        api_key="top-secret",
        model="model-x",
        max_tokens=10_000,
        timeout_seconds=30,
    )
    result = GenerationClient(config, transport=transport).generate(
        prompt="make code", output_dir=tmp_path
    )

    assert seen["url"] == "https://example.invalid/v1/messages"
    assert result.input_tokens == 120
    assert result.output_tokens == 80
    assert result.attempts == 1
    assert result.code.endswith("# === END ===")
    persisted = json.loads((tmp_path / "generation.json").read_text("utf-8"))
    assert "top-secret" not in json.dumps(persisted)


def test_generation_requires_an_end_marker(tmp_path):
    def transport(*args, **kwargs):
        return _Response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": "from manim import *\nclass Solution(Scene): pass",
                    }
                ]
            }
        )

    config = GenerationConfig("https://example.invalid", "secret", "m")
    with pytest.raises(GenerationFailed, match="END") as raised:
        GenerationClient(config, transport=transport).generate(
            prompt="make code", output_dir=tmp_path
        )
    assert raised.value.attempts == 2


def test_generation_retries_transient_transport_failure(tmp_path):
    calls = 0

    def transport(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.ConnectionError("temporary")
        return _Response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "from manim import *\n"
                            "class Solution(Scene): pass\n"
                            "# === END ==="
                        ),
                    }
                ]
            }
        )

    config = GenerationConfig(
        "https://example.invalid", "secret", "m", retry_delay_seconds=0
    )
    result = GenerationClient(config, transport=transport).generate(
        prompt="make code", output_dir=tmp_path
    )

    assert calls == 2
    assert result.attempts == 2


def test_generation_counts_usage_from_invalid_complete_response(tmp_path):
    calls = 0

    def transport(*args, **kwargs):
        nonlocal calls
        calls += 1
        text = "from manim import *\nclass Solution(Scene): pass"
        if calls == 2:
            text += "\n# === END ==="
        return _Response(
            {
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
        )

    config = GenerationConfig(
        "https://example.invalid", "secret", "m", retry_delay_seconds=0
    )
    result = GenerationClient(config, transport=transport).generate(
        prompt="make code", output_dir=tmp_path
    )

    assert result.input_tokens == 20
    assert result.output_tokens == 40


class _Response:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = json.dumps(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload
