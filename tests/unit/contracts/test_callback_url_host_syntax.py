from __future__ import annotations

import pytest
from contract_samples import submission_payload

from manim_quality.contracts import QualitySubmission


@pytest.mark.parametrize(
    "callback_url",
    [
        "https://exa mple.test/callback",
        "https://example.test/has space",
        "https://example.test/callback\r\nX-Test: injected",
        "https://example.test/callback\tsegment",
        "https://example.test/callback\x00segment",
        "https://example.test/callback\x7fsegment",
        "https://example.test/callback\u00a0segment",
    ],
)
def test_callback_url_rejects_raw_whitespace_and_control_characters(
    callback_url: str,
) -> None:
    _assert_rejected(callback_url)


@pytest.mark.parametrize(
    "callback_url",
    [
        "https:///callback",
        "https://./callback",
        "https://.example.test/callback",
        "https://example..test/callback",
        "https://example.test./callback",
        "https://-invalid.example/callback",
        "https://invalid-.example/callback",
        "https://invalid_label.example/callback",
        "https://exámple.test/callback",
        f"https://{'a' * 64}.example/callback",
        "https://[v1.foo]/callback",
    ],
)
def test_callback_url_rejects_invalid_dns_hosts(callback_url: str) -> None:
    _assert_rejected(callback_url)


@pytest.mark.parametrize(
    "callback_url",
    [
        "https://example.com/callback",
        "http://sub-domain.example.test:8080/callback",
        "https://xn--bcher-kva.example/callback",
        "http://localhost/callback",
        "http://127.0.0.1/callback",
        "https://192.0.2.1:8443/callback",
        "http://[::1]/callback",
        "https://[2001:db8::1]:8443/callback",
    ],
)
def test_callback_url_accepts_valid_dns_ipv4_and_bracketed_ipv6(
    callback_url: str,
) -> None:
    payload = submission_payload()
    payload["callback_url"] = callback_url

    assert QualitySubmission.from_dict(payload).callback_url == callback_url


def _assert_rejected(callback_url: str) -> None:
    payload = submission_payload()
    payload["callback_url"] = callback_url

    with pytest.raises(ValueError, match="callback_url"):
        QualitySubmission.from_dict(payload)
