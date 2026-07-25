from __future__ import annotations

import pytest
from contract_samples import submission_payload

from manim_quality.contracts import QualitySubmission, _json_values

MAX_JSON_DEPTH = 64


@pytest.mark.parametrize(
    "callback_url",
    [
        42,
        "ftp://example.test/callback",
        "https:///missing-host",
        "https://user@example.test/callback",
        "https://user:secret@example.test/callback",
        "https://example.test:not-a-port/callback",
        "/relative/callback",
    ],
)
def test_callback_url_rejects_unsafe_or_incomplete_authority(
    callback_url: object,
) -> None:
    payload = submission_payload()
    payload["callback_url"] = callback_url

    with pytest.raises((TypeError, ValueError), match="callback_url"):
        QualitySubmission.from_dict(payload)


@pytest.mark.parametrize(
    "callback_url",
    ["http://example.test/callback", "https://example.test:8443/callback?job=1"],
)
def test_callback_url_accepts_http_and_https_with_hostname(
    callback_url: str,
) -> None:
    payload = submission_payload()
    payload["callback_url"] = callback_url

    assert QualitySubmission.from_dict(payload).callback_url == callback_url


def test_planning_accepts_exactly_maximum_json_container_depth() -> None:
    payload = submission_payload()
    payload["planning"] = _nested_planning(MAX_JSON_DEPTH - 1)

    assert (
        QualitySubmission.from_dict(payload).to_dict()["planning"]
        == payload["planning"]
    )


def test_planning_rejects_json_beyond_maximum_depth() -> None:
    payload = submission_payload()
    payload["planning"] = _nested_planning(MAX_JSON_DEPTH)

    with pytest.raises(ValueError, match="planning.*depth"):
        QualitySubmission.from_dict(payload)


def test_recursive_planning_becomes_value_error_not_recursion_error() -> None:
    payload = submission_payload()
    recursive: dict[str, object] = {}
    recursive["self"] = recursive
    payload["planning"] = recursive

    with pytest.raises(ValueError, match="planning.*depth"):
        QualitySubmission.from_dict(payload)


def test_runtime_recursion_error_becomes_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = submission_payload()
    recursive: dict[str, object] = {}
    recursive["self"] = recursive
    payload["planning"] = recursive
    monkeypatch.setattr(_json_values, "MAX_JSON_DEPTH", 10_000)

    with pytest.raises(ValueError, match="planning.*depth"):
        QualitySubmission.from_dict(payload)


def _nested_planning(nested_lists: int) -> dict[str, object]:
    value: object = "leaf"
    for _ in range(nested_lists):
        value = [value]
    return {"value": value}
