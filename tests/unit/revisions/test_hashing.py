import hashlib

from manim_quality.revisions.fingerprint import (
    code_hash,
    evidence_hash,
    sha256_bytes,
    sha256_text,
)


def test_sha256_helpers_return_canonical_hashes() -> None:
    expected = f"sha256:{hashlib.sha256(b'quality').hexdigest()}"

    assert sha256_bytes(b"quality") == expected
    assert sha256_text("quality") == expected
    assert len(expected) == 71
    assert expected == expected.lower()


def test_code_hash_covers_the_full_source_text() -> None:
    source = "class Demo:\n    pass\n"

    assert code_hash(source) == sha256_text(source)
    assert code_hash(source + "\n") != code_hash(source)


def test_evidence_hash_binds_exact_evidence_bytes() -> None:
    evidence = b'{"checker":"logic-v1","result":"PASS"}'

    assert evidence_hash(evidence) == sha256_bytes(evidence)
    assert evidence_hash(evidence + b"\n") != evidence_hash(evidence)
