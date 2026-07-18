"""Repairability route constant sets."""

AUTO_READY_CONTRACT_KINDS = frozenset(
    {
        "equal_length",
        "intersection",
        "right_triangle_numeric_model",
        "distance_between_points",
        "axis_guide_orientation",
        "point_coordinate",
        "perpendicular_lines",
        "source_contains",
        "source_not_contains",
        "must_contain",
        "must_not_contain",
        "forbid_text",
        "no_unescaped_latex_command",
        "point_on_line",
        "reflection_point",
        "angle_measure",
        "line_endpoint_match",
        "foot_point",
        "line_intersection",
        "points_collinear",
        "line_perpendicular",
        "angle_equals_degrees",
        "angle_equals_angle",
        "length_equals_length",
    }
)

SOURCE_LEVEL_CONTRACT_KINDS = frozenset(
    {
        "source_contains",
        "source_not_contains",
        "must_contain",
        "must_not_contain",
        "forbid_text",
        "no_unescaped_latex_command",
    }
)

GEOMETRY_STRUCTURAL_CONTRACT_KINDS = frozenset(
    {
        "point_on_line",
        "reflection_point",
        "angle_measure",
        "line_endpoint_match",
        "foot_point",
        "line_intersection",
        "points_collinear",
        "line_perpendicular",
        "angle_equals_degrees",
        "angle_equals_angle",
        "length_equals_length",
    }
)
