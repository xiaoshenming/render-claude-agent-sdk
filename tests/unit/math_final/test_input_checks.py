import hashlib

from manim_quality.math_final.input_checks import inspect_input_identity


def test_matching_source_identity_is_clean():
    source = "value = 1\n"
    evidence = inspect_input_identity(
        problem_text="已知 value，求值。",
        source=source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
    )
    assert evidence == ()


def test_sha_mismatch_is_deterministic_source_mismatch():
    evidence = inspect_input_identity(
        problem_text="题目",
        source="value = 1\n",
        expected_sha256="0" * 64,
    )
    assert evidence[0].code == "SOURCE_SHA_MISMATCH"
    assert evidence[0].status == "source_mismatch"
    assert evidence[0].deterministic is True
