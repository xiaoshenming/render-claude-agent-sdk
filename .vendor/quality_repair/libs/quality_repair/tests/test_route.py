from libs.quality_repair.route import classify


SAFE_AREA = {"x_min": -7.1, "x_max": 7.1, "y_min": -4.0, "y_max": 4.0}


def test_logic_whitelisted_list_coords_inside_safe_area_auto_ready():
    decision = classify(
        "logic",
        {"kind": "intersection", "expected_coords": [1, 2]},
        SAFE_AREA,
    )

    assert decision.classification == "auto_ready"
    assert decision.reasons == []


def test_logic_kind_not_whitelisted_detect_only_with_kind_reason():
    decision = classify(
        "logic",
        {"kind": "slope_text_proof", "expected_value": 2},
        SAFE_AREA,
    )

    assert decision.classification == "detect_only"
    assert decision.reasons == ["kind_not_whitelisted:slope_text_proof"]


def test_logic_missing_expected_value_detect_only():
    decision = classify("logic", {"kind": "equal_length"}, SAFE_AREA)

    assert decision.classification == "detect_only"
    assert decision.reasons == ["no_expected_value"]


def test_logic_source_contains_with_numeric_expected_auto_ready():
    decision = classify(
        "logic",
        {"kind": "source_contains", "text": "6\\sqrt{3}", "expected_value": 6 * 3**0.5},
        SAFE_AREA,
    )

    assert decision.classification == "auto_ready"
    assert decision.reasons == []


def test_logic_expected_coords_outside_safe_area_detect_only():
    decision = classify(
        "logic",
        {"kind": "point_coordinate", "expected_coords": [40, 0]},
        SAFE_AREA,
    )

    assert decision.classification == "detect_only"
    assert decision.reasons == ["expected_out_of_safe_area"]


def test_logic_voiceover_refs_unknown_text_dependency():
    decision = classify(
        "logic",
        {
            "kind": "equal_length",
            "expected_length": 3,
            "voiceover_refs": ["intro"],
        },
        SAFE_AREA,
    )

    assert decision.classification == "unknown"
    assert decision.reasons == ["unmodeled_text_dependency"]


def test_layout_profile_auto_ready_passthrough():
    decision = classify("layout", None, SAFE_AREA)

    assert decision.classification == "auto_ready"
    assert decision.reasons == []


def test_unsupported_profile_returns_unknown_with_reason():
    decision = classify("pre_render", None, SAFE_AREA)

    assert decision.classification == "unknown"
    assert decision.reasons == ["unsupported_profile:pre_render"]


def test_invalid_logic_contract_returns_classify_error_without_raising():
    decision = classify("logic", "bad contract", SAFE_AREA)  # type: ignore[arg-type]

    assert decision.classification == "unknown"
    assert len(decision.reasons) == 1
    assert decision.reasons[0].startswith("classify_error:")


def test_logic_expected_coords_dict_and_nested_expected_coords_auto_ready():
    dict_decision = classify(
        "logic",
        {"kind": "point_coordinate", "expected_coords": {"x": 1, "y": 2}},
        SAFE_AREA,
    )
    nested_decision = classify(
        "logic",
        {"kind": "point_coordinate", "expected": {"coords": [1, 2]}},
        SAFE_AREA,
    )

    assert dict_decision.classification == "auto_ready"
    assert dict_decision.reasons == []
    assert nested_decision.classification == "auto_ready"
    assert nested_decision.reasons == []


def test_logic_audit_contract_context_auto_ready_after_normalization():
    decision = classify(
        "logic",
        {
            "contracts": [
                {
                    "kind": "equal_length",
                    "segment_a": ["p1", "p2"],
                    "segment_b": ["p3", "p4"],
                    "move_point": "p4",
                }
            ],
            "before_validation": {
                "issues": [
                    {
                        "kind": "equal_length_wrong",
                        "target": "p4",
                        "evidence": {
                            "expected_coords": [3.8671603823699967, -1.8531358470520014, 0.0],
                            "actual_coords": [4.0, -1.8, 0.0],
                        },
                    }
                ]
            },
        },
        SAFE_AREA,
    )

    assert decision.classification == "auto_ready"
    assert decision.reasons == []


def test_logic_contracts_point_coordinate_auto_ready_after_normalization():
    decision = classify(
        "logic",
        {
            "contracts": [
                {
                    "kind": "point_coordinate",
                    "target": "dot_P1",
                    "expected_coords": [-1.0, 0.0, 0.0],
                }
            ]
        },
        SAFE_AREA,
    )

    assert decision.classification == "auto_ready"
    assert decision.reasons == []


def test_logic_source_level_latex_contract_auto_ready():
    decision = classify(
        "logic",
        {"kind": "no_unescaped_latex_command", "line": 1354, "text": "\\dfrac"},
        SAFE_AREA,
    )

    assert decision.classification == "auto_ready"
    assert decision.reasons == []


def test_logic_proof_geometry_contracts_auto_ready():
    contracts = [
        {"kind": "foot_point", "target": "N_rand", "source": "B_prime", "line": ["A", "B"]},
        {"kind": "line_intersection", "target": "M_rand", "line_a": ["A", "D"], "line_b": ["B_prime", "N_rand"]},
        {"kind": "points_collinear", "points": ["B_prime", "M_rand", "N_rand"]},
        {"kind": "line_perpendicular", "line_a": ["B_prime", "N_rand"], "line_b": ["A", "B"]},
        {"kind": "angle_equals_degrees", "points": ["A", "F", "E"], "expected_degrees": 35},
        {"kind": "angle_equals_angle", "points": ["A", "F", "E"], "reference_points": ["A", "C", "B"]},
        {"kind": "length_equals_length", "segment_a": ["B", "F"], "segment_b": ["B", "E"]},
    ]

    for contract in contracts:
        decision = classify("logic", contract, SAFE_AREA)
        assert decision.classification == "auto_ready", contract
        assert decision.reasons == []
