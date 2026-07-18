import pytest

from manim_quality.logic.expectations.schemas import (
    expected_relation_output_schema,
    parse_expected_relation_contract,
)


def valid_payload():
    return {
        "schema_version": "manim-quality.expected-relations.v1",
        "claims": [
            {
                "claim_id": "claim-1",
                "relation": "perpendicular",
                "operands": ["AD", "BC"],
                "source_kind": "problem",
                "evidence": "AD perpendicular BC at D",
                "confidence": "explicit",
            }
        ],
    }


def test_parses_strict_expected_relation_contract() -> None:
    contract = parse_expected_relation_contract(valid_payload())
    schema = expected_relation_output_schema()

    assert contract.claims[0].operands == ("AD", "BC")
    assert contract.claims[0].relation == "perpendicular"
    assert schema["additionalProperties"] is False
    assert "const" not in repr(schema)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relation", "distance"),
        ("operands", ["AD"]),
        ("evidence", ""),
        ("source_kind", "candidate"),
        ("confidence", "guessed"),
    ],
)
def test_rejects_unsupported_or_unproven_claim_fields(field, value) -> None:
    payload = valid_payload()
    payload["claims"][0][field] = value

    with pytest.raises(ValueError):
        parse_expected_relation_contract(payload)


def test_rejects_duplicate_claim_ids_and_repair_hints() -> None:
    payload = valid_payload()
    payload["claims"].append(dict(payload["claims"][0]))

    with pytest.raises(ValueError, match="duplicate"):
        parse_expected_relation_contract(payload)

    payload = valid_payload()
    payload["claims"][0]["repair_hint"] = "change D to C"
    with pytest.raises(ValueError):
        parse_expected_relation_contract(payload)


@pytest.mark.parametrize(
    ("relation", "operands"),
    [
        ("point_coordinate", ["O", "0", "0.5", "0"]),
        ("segment_length", ["AC", "4"]),
        ("intersection", ["O", "AC", "BD"]),
    ],
)
def test_parses_generic_numeric_geometry_relations(relation, operands) -> None:
    payload = valid_payload()
    payload["claims"][0]["relation"] = relation
    payload["claims"][0]["operands"] = operands

    contract = parse_expected_relation_contract(payload)

    assert contract.claims[0].relation == relation
    assert contract.claims[0].operands == tuple(operands)


@pytest.mark.parametrize(
    ("relation", "operands"),
    [
        ("point_coordinate", ["O", "nan", "0.5", "0"]),
        ("segment_length", ["AC", "infinity"]),
    ],
)
def test_rejects_non_finite_numeric_relation_operands(relation, operands) -> None:
    payload = valid_payload()
    payload["claims"][0]["relation"] = relation
    payload["claims"][0]["operands"] = operands

    with pytest.raises(ValueError, match="finite"):
        parse_expected_relation_contract(payload)
