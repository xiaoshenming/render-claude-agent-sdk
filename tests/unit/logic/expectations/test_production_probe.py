from evals._production_relation_probe import contract_payload


def test_maps_generic_production_contracts_without_repair_hints() -> None:
    payload = contract_payload(
        "PLOGIC-TEST",
        [
            {
                "kind": "intersection",
                "point": "O",
                "line1_points": ["A", "C"],
                "line2_points": ["B", "D"],
            },
            {
                "kind": "distance_between_points",
                "points": ["A", "C"],
                "expected_length": 3,
                "move_point": "A",
            },
            {
                "kind": "perpendicular_lines",
                "line1_points": ["A", "B"],
                "line2_points": ["A", "D"],
                "move_point": "D",
            },
        ],
    )

    assert [item["relation"] for item in payload["claims"]] == [
        "intersection",
        "segment_length",
        "perpendicular",
    ]
    assert payload["claims"][1]["operands"] == ["AC", "3"]
    assert "move_point" not in repr(payload)


def test_maps_coordinate_and_collinearity_contracts() -> None:
    payload = contract_payload(
        "PLOGIC-TEST",
        [
            {
                "kind": "point_coordinate",
                "point": "A",
                "expected_coords": [0, 3, 0],
            },
            {
                "kind": "collinearity_model",
                "point": "B",
                "line_points": ["A", "C"],
                "max_displacement": 0.2,
            },
        ],
    )

    assert payload["claims"][0]["operands"] == ["A", "0", "3", "0"]
    assert payload["claims"][1]["operands"] == ["A", "B", "C"]


def test_preserves_multi_character_point_names_in_segment_reference() -> None:
    payload = contract_payload(
        "PLOGIC-TEST",
        [
            {
                "kind": "distance_between_points",
                "points": ["A_p", "C_p"],
                "expected_length": 4,
            }
        ],
    )

    assert payload["claims"][0]["operands"] == ["A_p:C_p", "4"]
