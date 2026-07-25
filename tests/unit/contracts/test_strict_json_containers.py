from __future__ import annotations

import json
from collections import UserDict, UserList
from collections.abc import Callable

import pytest
from contract_samples import (
    CONTRACT_CASES,
    HASH_A,
    Deserializer,
    PayloadFactory,
    result_payload,
    revision_payload,
    submission_payload,
)

from manim_quality.contracts import QualityResult, QualitySubmission, Revision


@pytest.mark.parametrize(("name", "deserialize", "payload_factory"), CONTRACT_CASES)
def test_from_dict_rejects_custom_top_level_mapping(
    name: str,
    deserialize: Deserializer,
    payload_factory: PayloadFactory,
) -> None:
    with pytest.raises(TypeError, match="JSON object"):
        deserialize(UserDict(payload_factory()))


STRICT_CONTAINER_CASES = (
    (
        "submission planning mapping",
        QualitySubmission.from_dict,
        submission_payload,
        "planning",
        lambda: UserDict({"scene": "SceneA"}),
    ),
    (
        "submission nested tuple",
        QualitySubmission.from_dict,
        submission_payload,
        "planning",
        lambda: {"scenes": ("SceneA",)},
    ),
    (
        "submission nested custom sequence",
        QualitySubmission.from_dict,
        submission_payload,
        "planning",
        lambda: {"scenes": UserList(["SceneA"])},
    ),
    (
        "submission nested custom mapping",
        QualitySubmission.from_dict,
        submission_payload,
        "planning",
        lambda: {"scene": UserDict({"id": "SceneA"})},
    ),
    (
        "revision scene hashes mapping",
        Revision.from_dict,
        revision_payload,
        "scene_hashes",
        lambda: UserDict({"SceneA": HASH_A}),
    ),
    (
        "revision changed scenes tuple",
        Revision.from_dict,
        revision_payload,
        "changed_scene_ids",
        lambda: ("SceneA",),
    ),
    (
        "revision changed scenes custom sequence",
        Revision.from_dict,
        revision_payload,
        "changed_scene_ids",
        lambda: UserList(["SceneA"]),
    ),
    (
        "result warnings tuple",
        QualityResult.from_dict,
        result_payload,
        "warnings",
        lambda: ("warning",),
    ),
    (
        "result warnings custom sequence",
        QualityResult.from_dict,
        result_payload,
        "warnings",
        lambda: UserList(["warning"]),
    ),
    (
        "result token usage mapping",
        QualityResult.from_dict,
        result_payload,
        "token_usage",
        lambda: UserDict({"reviewer": 10}),
    ),
    (
        "result timings mapping",
        QualityResult.from_dict,
        result_payload,
        "timings_ms",
        lambda: UserDict({"reviewer": 20}),
    ),
)


@pytest.mark.parametrize(
    ("name", "deserialize", "payload_factory", "field_name", "invalid_factory"),
    STRICT_CONTAINER_CASES,
)
def test_from_dict_accepts_only_native_json_containers(
    name: str,
    deserialize: Deserializer,
    payload_factory: PayloadFactory,
    field_name: str,
    invalid_factory: Callable[[], object],
) -> None:
    payload = payload_factory()
    payload[field_name] = invalid_factory()

    with pytest.raises(TypeError, match=field_name):
        deserialize(payload)


@pytest.mark.parametrize(("name", "deserialize", "payload_factory"), CONTRACT_CASES)
def test_to_dict_contains_only_native_json_containers(
    name: str,
    deserialize: Deserializer,
    payload_factory: PayloadFactory,
) -> None:
    payload = deserialize(payload_factory()).to_dict()  # type: ignore[attr-defined]

    _assert_native_json(payload)
    json.dumps(payload)


def _assert_native_json(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            assert type(key) is str
            _assert_native_json(item)
        return
    if type(value) is list:
        for item in value:
            _assert_native_json(item)
        return
    assert type(value) in {type(None), bool, int, float, str}
