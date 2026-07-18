"""Deterministic layout prepatches for high-confidence Manim overlap patterns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(kw_only=True)
class DeterministicPatchReport:
    changed: bool
    patch_names: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    before_code: str = ""
    after_code: str = ""


def apply_layout_prepatch(workdir: Path) -> DeterministicPatchReport:
    """Apply conservative candidate.py patches derived from layout_repair_brief.json."""
    candidate = workdir / "candidate.py"
    try:
        before = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        return DeterministicPatchReport(changed=False, reasons=[f"candidate_unreadable:{exc}"])
    brief = _read_brief(workdir / "layout_repair_brief.json")
    failure_types = _high_confidence_failure_types(brief)
    after = before
    patch_names: list[str] = []

    if "label_shape_overlap" in failure_types:
        label_direction_hints = _label_direction_hints(brief)
        after, changed = _patch_label_shape_overlap_helpers(after)
        if changed:
            patch_names.append("label_shape_overlap_helper_buff")
        after, changed = _patch_label_avoid_overlap_geometry(after)
        if changed:
            patch_names.append("label_avoid_overlap_geometry")
        after, changed = _patch_make_point_label_radial_direction(after)
        if changed:
            patch_names.append("make_point_label_radial_direction")
        after, changed = _patch_point_label_callsite_directions(after, label_direction_hints)
        if changed:
            patch_names.append("point_label_callsite_directions")
        after, changed = _patch_direct_text_label_directions(after, label_direction_hints)
        if changed:
            patch_names.append("label_shape_direct_text_label_directions")
        after, changed = _patch_label_obstacles_from_existing_geometry(after)
        if changed:
            patch_names.append("label_obstacles_from_existing_geometry")
        label_obstacle_targets = _short_label_texts_from_brief(brief)
        if label_obstacle_targets:
            after, changed = _patch_short_label_obstacles_from_existing_labels(
                after,
                {text: "" for text in label_obstacle_targets},
            )
            if changed:
                patch_names.append("label_obstacles_from_existing_labels")
        after, changed = _patch_label_before_line_creation(after)
        if changed:
            patch_names.append("label_before_line_creation")
        after, changed = _patch_panel_vertical_spacing(after)
        if changed:
            patch_names.append("panel_vertical_spacing")

    short_label_direction_hints = _short_label_text_overlap_direction_hints(brief)
    if short_label_direction_hints:
        after, changed = _patch_point_label_callsite_directions(after, short_label_direction_hints)
        if changed:
            patch_names.append("short_label_text_overlap_directions")
        after, changed = _patch_direct_text_label_directions(after, short_label_direction_hints)
        if changed:
            patch_names.append("direct_text_label_directions")
        after, changed = _patch_short_label_obstacles_from_existing_labels(after, short_label_direction_hints)
        if changed:
            patch_names.append("short_label_obstacles_from_existing_labels")

    if "same_origin_text_stack" in failure_types:
        after, changed = _patch_multiple_choice_option_row(after)
        if changed:
            patch_names.append("multiple_choice_option_row_arrange")

    if _brief_has_text_bounds_overflow(brief):
        after, changed = _patch_make_label_text_safe_box_clamp(after)
        if changed:
            patch_names.append("make_label_text_safe_box_clamp")

    if _brief_has_text_container_overflow(brief):
        after, changed = _patch_left_knowledge_card_fit(after)
        if changed:
            patch_names.append("left_knowledge_card_fit")

    if _brief_has_formula_stack_pressure(brief):
        after, changed = _patch_formula_stack_compaction(after)
        if changed:
            patch_names.append("formula_stack_compaction")
        after, changed = _patch_mathtex_scale_font_size_misuse(after)
        if changed:
            patch_names.append("mathtex_scale_font_size_misuse")
        after, changed = _patch_formula_stack_board_lifecycle(after)
        if changed:
            patch_names.append("formula_stack_board_lifecycle")
        after, changed = _patch_formula_stack_board_motion(after)
        if changed:
            patch_names.append("formula_stack_board_motion")
        after, changed = _patch_right_panel_formula_lifecycle(after)
        if changed:
            patch_names.append("right_panel_formula_lifecycle")
        after, changed = _patch_option_analysis_table_spacing(after)
        if changed:
            patch_names.append("option_analysis_table_spacing")
        after, changed = _patch_local_formula_stack_spacing(after)
        if changed:
            patch_names.append("local_formula_stack_spacing")

    after, changed = _patch_right_rule_condition_spacing(after)
    if changed:
        patch_names.append("right_rule_condition_spacing")
    after, changed = _patch_summary_panel_fades_step_formulas(after)
    if changed:
        patch_names.append("summary_panel_fades_step_formulas")

    if "step_panel_lifecycle_accumulation" in failure_types:
        after, changed = _patch_problem_panel_fade_before_first_step(after)
        if changed:
            patch_names.append("problem_panel_fade_before_first_step_panel")
        after, changed = _patch_step_panel_sequence_fade_previous(after)
        if changed:
            patch_names.append("step_panel_sequence_fade_previous")

    if after == before:
        return DeterministicPatchReport(changed=False, patch_names=[], before_code=before, after_code=before)
    candidate.write_text(after, encoding="utf-8")
    return DeterministicPatchReport(changed=True, patch_names=patch_names, before_code=before, after_code=after)


def _read_brief(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _high_confidence_failure_types(brief: dict[str, Any], *, min_confidence: float = 0.7) -> set[str]:
    found: set[str] = set()
    clusters = brief.get("clusters") if isinstance(brief.get("clusters"), list) else []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        if _confidence(cluster) < min_confidence:
            continue
        failure_type = str(cluster.get("failure_type") or "")
        if failure_type:
            found.add(failure_type)
    if found:
        return found
    summary = brief.get("summary") if isinstance(brief.get("summary"), dict) else {}
    if _confidence(summary, key="primary_confidence") >= min_confidence:
        failure_type = str(summary.get("primary_failure_type") or "")
        if failure_type:
            found.add(failure_type)
    return found


def _confidence(data: dict[str, Any], *, key: str = "confidence") -> float:
    try:
        return float(data.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _patch_label_shape_overlap_helpers(code: str) -> tuple[str, bool]:
    patched = code
    patched = re.sub(
        r"def avoid_overlap\(([^)]*?)buff\s*=\s*0\.1([^)]*?)\):",
        r"def avoid_overlap(\1buff=0.25\2):",
        patched,
        count=1,
    )
    patched = patched.replace(
        "directions = [direction, UL, UR, DL, DR, UP, DOWN, LEFT, RIGHT]",
        "directions = [direction, LEFT, RIGHT, UP, DOWN, UL, UR, DL, DR]",
        1,
    )
    patched = re.sub(
        r"(return\s+self\.avoid_overlap\([^\n]*?buff\s*=\s*)0\.\d+",
        r"\g<1>0.45",
        patched,
        count=1,
    )
    return patched, patched != code


def _patch_make_label_text_safe_box_clamp(code: str) -> tuple[str, bool]:
    if "safe_left, safe_right = -6.35, 6.35" in code:
        return code, False
    pattern = re.compile(
        r"(?m)^(?P<indent>\s*)mob\.next_to\(anchor_mob,\s*direction,\s*buff=buff\)\n"
        r"(?P<return_indent>\s*)return mob$"
    )
    match = pattern.search(code)
    if not match:
        return code, False
    indent = match.group("indent")
    return_indent = match.group("return_indent")
    clamp = (
        f"{indent}mob.next_to(anchor_mob, direction, buff=buff)\n"
        f"{indent}safe_left, safe_right = -6.35, 6.35\n"
        f"{indent}safe_bottom, safe_top = -3.35, 3.35\n"
        f"{indent}if mob.get_left()[0] < safe_left:\n"
        f"{indent}    mob.shift(RIGHT * (safe_left - mob.get_left()[0]))\n"
        f"{indent}if mob.get_right()[0] > safe_right:\n"
        f"{indent}    mob.shift(LEFT * (mob.get_right()[0] - safe_right))\n"
        f"{indent}if mob.get_bottom()[1] < safe_bottom:\n"
        f"{indent}    mob.shift(UP * (safe_bottom - mob.get_bottom()[1]))\n"
        f"{indent}if mob.get_top()[1] > safe_top:\n"
        f"{indent}    mob.shift(DOWN * (mob.get_top()[1] - safe_top))\n"
        f"{return_indent}return mob"
    )
    return code[: match.start()] + clamp + code[match.end() :], True


def _patch_multiple_choice_option_row(code: str) -> tuple[str, bool]:
    if "multiple_choice_option_row_arrange" in code:
        return code, False
    pattern = re.compile(r"self\.make_formula_row\((?P<body>[^()\n]*(?:\n\s*[^()\n]*)*)\)", re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        body = match.group("body")
        options = re.findall(r'"([A-D]\.\s*[^"]+)"', body)
        if len(options) < 4:
            return match.group(0)
        option_lines = ",\n".join(f"                self.make_formula_row({_source_string_literal(option)})" for option in options[:4])
        return f"# multiple_choice_option_row_arrange\n            VGroup(\n{option_lines}\n            ).arrange(RIGHT, buff=0.62)"

    patched = pattern.sub(replace, code)
    return patched, patched != code


def _source_string_literal(value: str) -> str:
    return '"' + value.replace('"', r'\"') + '"'


def _patch_left_knowledge_card_fit(code: str) -> tuple[str, bool]:
    if "left_knowledge_card_fit" in code:
        return code, False
    marker = "left_card = VGroup(left_box, left_title, props, principle)"
    if marker not in code or "left_box = RoundedRectangle" not in code:
        return code, False
    insert = (
        "        # left_knowledge_card_fit\n"
        "        card_inner_width = left_box.width - 0.56\n"
        "        for mob in (props, principle):\n"
        "            if mob.width > card_inner_width and mob.width > 0:\n"
        "                mob.scale_to_fit_width(card_inner_width)\n"
        "        props.next_to(left_title, DOWN, buff=0.3).align_to(left_box, LEFT).shift(RIGHT * 0.28)\n"
        "        principle.next_to(props, DOWN, buff=0.25).align_to(left_box, LEFT).shift(RIGHT * 0.28)\n"
        "        if principle.get_bottom()[1] < left_box.get_bottom()[1] + 0.24:\n"
        "            principle.shift(UP * (left_box.get_bottom()[1] + 0.24 - principle.get_bottom()[1]))\n"
    )
    return code.replace(f"        {marker}", insert + f"        {marker}", 1), True


def _patch_panel_vertical_spacing(code: str) -> tuple[str, bool]:
    patched = code
    replacements = (
        (
            r"(problem_options\s*=\s*VGroup\(row1,\s*row2\)\.arrange\(DOWN,\s*aligned_edge\s*=\s*LEFT,\s*buff\s*=\s*)0\.3",
            r"\g<1>0.5",
        ),
        (
            r"(problem_panel\s*=\s*VGroup\(problem_title,\s*problem_options\)\.arrange\(DOWN,\s*aligned_edge\s*=\s*LEFT,\s*buff\s*=\s*)0\.3",
            r"\g<1>0.45",
        ),
        (
            r"(\bpanel_[A-Za-z0-9_]*\s*=\s*VGroup\([\s\S]*?\)\.arrange\(DOWN,\s*aligned_edge\s*=\s*LEFT,\s*buff\s*=\s*)0\.25",
            r"\g<1>0.36",
        ),
    )
    for pattern, replacement in replacements:
        patched = re.sub(pattern, replacement, patched)
    return patched, patched != code


def _patch_label_avoid_overlap_geometry(code: str) -> tuple[str, bool]:
    match = re.search(
        r"(?ms)^(?P<indent>\s*)def avoid_overlap\(self, label, anchor, obstacles=None, directions=None, buff=[^)]+\):\n"
        r"(?P<body>.*?)(?=^\s*def make_point_label\()",
        code,
    )
    if not match:
        return code, False
    indent = match.group("indent")
    body = indent + "    "
    replacement = f"""{indent}def avoid_overlap(self, label, anchor, obstacles=None, directions=None, buff=0.25):
{body}obstacles = list(obstacles or [])
{body}base_directions = list(directions) if directions is not None else [UR, UL, DR, DL, UP, DOWN, RIGHT, LEFT]
{body}directions = []
{body}for item in base_directions:
{body}    if not any(np.allclose(item, existing) for existing in directions):
{body}        directions.append(item)

{body}def iter_obstacles(items):
{body}    for item in items:
{body}        if item is None:
{body}            continue
{body}        if item.__class__.__name__ in {{"Line", "Arrow"}}:
{body}            yield item
{body}        children = list(getattr(item, "submobjects", []) or [])
{body}        if children:
{body}            yield from iter_obstacles(children)
{body}        else:
{body}            yield item

{body}def bbox_overlap(cand, obs):
{body}    try:
{body}        return (
{body}            cand.get_right()[0] > obs.get_left()[0]
{body}            and cand.get_left()[0] < obs.get_right()[0]
{body}            and cand.get_top()[1] > obs.get_bottom()[1]
{body}            and cand.get_bottom()[1] < obs.get_top()[1]
{body}        )
{body}    except Exception:
{body}        return False

{body}def rect_edges(cand):
{body}    left = float(cand.get_left()[0])
{body}    right = float(cand.get_right()[0])
{body}    top = float(cand.get_top()[1])
{body}    bottom = float(cand.get_bottom()[1])
{body}    points = [(left, bottom), (right, bottom), (right, top), (left, top)]
{body}    return points, list(zip(points, points[1:] + points[:1]))

{body}def point_in_rect(point, rect_points):
{body}    xs = [p[0] for p in rect_points]
{body}    ys = [p[1] for p in rect_points]
{body}    return min(xs) <= float(point[0]) <= max(xs) and min(ys) <= float(point[1]) <= max(ys)

{body}def orientation(a, b, c):
{body}    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

{body}def on_segment(a, b, c):
{body}    return (
{body}        min(a[0], c[0]) - 1e-7 <= b[0] <= max(a[0], c[0]) + 1e-7
{body}        and min(a[1], c[1]) - 1e-7 <= b[1] <= max(a[1], c[1]) + 1e-7
{body}        and abs(orientation(a, b, c)) <= 1e-7
{body}    )

{body}def segments_intersect(a1, a2, b1, b2):
{body}    o1 = orientation(a1, a2, b1)
{body}    o2 = orientation(a1, a2, b2)
{body}    o3 = orientation(b1, b2, a1)
{body}    o4 = orientation(b1, b2, a2)
{body}    if o1 * o2 < 0 and o3 * o4 < 0:
{body}        return True
{body}    return on_segment(a1, b1, a2) or on_segment(a1, b2, a2) or on_segment(b1, a1, b2) or on_segment(b1, a2, b2)

{body}def line_close(cand, obs):
{body}    if obs.__class__.__name__ not in {{"Line", "Arrow"}}:
{body}        return False
{body}    try:
{body}        if hasattr(obs, "get_num_points") and obs.get_num_points() <= 0:
{body}            return False
{body}        p = cand.get_center()
{body}        a = obs.get_start()
{body}        b = obs.get_end()
{body}        ab = b - a
{body}        denom = float(np.dot(ab, ab))
{body}        if denom <= 1e-9:
{body}            return False
{body}        start = (float(a[0]), float(a[1]))
{body}        end = (float(b[0]), float(b[1]))
{body}        rect_points, edges = rect_edges(cand)
{body}        if point_in_rect(start, rect_points) or point_in_rect(end, rect_points):
{body}            return True
{body}        if any(segments_intersect(start, end, edge_start, edge_end) for edge_start, edge_end in edges):
{body}            return True
{body}        t = max(0.0, min(1.0, float(np.dot(p - a, ab) / denom)))
{body}        closest = a + t * ab
{body}        threshold = max(0.2, min(0.35, max(cand.width, cand.height) * 0.55))
{body}        return float(np.linalg.norm(p - closest)) < threshold
{body}    except Exception:
{body}        return False

{body}flat_obstacles = list(iter_obstacles(obstacles))
{body}best = None
{body}best_score = -10**9
{body}for direction in directions:
{body}    candidate = label.copy()
{body}    candidate.next_to(anchor, direction, buff=buff)
{body}    penalty = 0
{body}    for obstacle in flat_obstacles:
{body}        if obstacle.__class__.__name__ in {{"Line", "Arrow"}}:
{body}            if line_close(candidate, obstacle):
{body}                penalty += 120
{body}        elif bbox_overlap(candidate, obstacle):
{body}            penalty += 100
{body}    if candidate.get_left()[0] < -6.35 or candidate.get_right()[0] > 6.35 or candidate.get_bottom()[1] < -3.35 or candidate.get_top()[1] > 3.35:
{body}        penalty += 50
{body}    try:
{body}        distance = float(np.linalg.norm(candidate.get_center() - anchor.get_center()))
{body}    except Exception:
{body}        distance = 0.0
{body}    score = -penalty - distance * 0.01
{body}    if score > best_score:
{body}        best = candidate
{body}        best_score = score
{body}if best is not None:
{body}    label.move_to(best.get_center())
{body}return label

"""
    patched = code[: match.start()] + replacement + code[match.end() :]
    return patched, patched != code


def _patch_make_point_label_radial_direction(code: str) -> tuple[str, bool]:
    match = re.search(
        r"(?ms)^(?P<indent>\s*)def make_point_label\(self, text, dot_or_point, direction=UR, color=None, obstacles=None\):\n"
        r"(?P<body>.*?)(?=^\s*def (?:_format_coord_value|make_unknown_point_label|make_point_coord_label)\(|\Z)",
        code,
    )
    if not match:
        return code, False
    indent = match.group("indent")
    body = indent + "    "
    replacement = f"""{indent}def make_point_label(self, text, dot_or_point, direction=UR, color=None, obstacles=None):
{body}label = self.make_label_text(text, color=color)
{body}anchor = dot_or_point if isinstance(dot_or_point, Mobject) else Dot(dot_or_point, radius=0.001, fill_opacity=0, stroke_opacity=0)
{body}preferred_direction = direction
{body}try:
{body}    origin = getattr(self, "_axis_origin", ORIGIN)
{body}    radial = anchor.get_center() - origin
{body}    norm = float(np.linalg.norm(radial))
{body}    if norm > 0.2:
{body}        preferred_direction = radial / norm
{body}except Exception:
{body}    preferred_direction = direction
{body}axis_directions = []
{body}coordinate_label = False
{body}try:
{body}    match = re.search(r"\\((-?\\d+(?:\\.\\d+)?),\\s*(-?\\d+(?:\\.\\d+)?)\\)", str(text).replace(" ", ""))
{body}    if match:
{body}        coordinate_label = True
{body}        x_value = float(match.group(1))
{body}        y_value = float(match.group(2))
{body}        if abs(y_value) < 1e-9:
{body}            if x_value >= 0:
{body}                axis_directions.extend([UR, DR, UP, DOWN, UL, DL])
{body}            else:
{body}                axis_directions.extend([UL, DL, UP, DOWN, UR, DR])
{body}        if abs(x_value) < 1e-9:
{body}            if y_value >= 0:
{body}                axis_directions.extend([UL, UR, LEFT, RIGHT, DL, DR])
{body}            else:
{body}                axis_directions.extend([DL, DR, LEFT, RIGHT, UL, UR])
{body}except Exception:
{body}    axis_directions = []
{body}numbered_label = False
{body}try:
{body}    numbered_label = bool(re.match(r"^[A-Za-z][₀₁₂₃₄₅₆₇₈₉0-9_]", str(text).replace("{{", "").replace("}}", ""))) and not coordinate_label
{body}except Exception:
{body}    numbered_label = False
{body}if axis_directions:
{body}    directions = axis_directions + [direction, preferred_direction]
{body}elif numbered_label:
{body}    directions = [direction]
{body}else:
{body}    directions = [preferred_direction, direction, LEFT, RIGHT, UP, DOWN, UL, UR, DL, DR]
{body}label_buff = 1.15 if numbered_label else 0.75 if coordinate_label else 0.45
{body}placed = self.avoid_overlap(label, anchor, obstacles=obstacles, directions=directions, buff=label_buff)
{body}try:
{body}    if placed.get_left()[0] < -6.35:
{body}        placed.shift(RIGHT * (-6.35 - placed.get_left()[0]))
{body}    if placed.get_right()[0] > 6.35:
{body}        placed.shift(LEFT * (placed.get_right()[0] - 6.35))
{body}    if placed.get_bottom()[1] < -3.35:
{body}        placed.shift(UP * (-3.35 - placed.get_bottom()[1]))
{body}    if placed.get_top()[1] > 3.35:
{body}        placed.shift(DOWN * (placed.get_top()[1] - 3.35))
{body}except Exception:
{body}    pass
{body}return placed

"""
    patched = code[: match.start()] + replacement + code[match.end() :]
    return patched, patched != code


def _label_direction_hints(brief: dict[str, Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for cluster in brief.get("clusters") if isinstance(brief.get("clusters"), list) else []:
        if not isinstance(cluster, dict) or str(cluster.get("failure_type") or "") != "label_shape_overlap":
            continue
        for item in cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []:
            if not isinstance(item, dict):
                continue
            objects = item.get("objects") if isinstance(item.get("objects"), list) else []
            text_obj = next((obj for obj in objects if isinstance(obj, dict) and obj.get("text")), None)
            shape_obj = next((obj for obj in objects if isinstance(obj, dict) and not obj.get("text")), None)
            if not text_obj or not shape_obj:
                continue
            text = str(text_obj.get("text") or "").strip()
            if _is_numbered_point_name(text):
                continue
            text_center = _center_from_evidence(text_obj)
            shape_center = _center_from_evidence(shape_obj)
            if not text or not text_center or not shape_center:
                continue
            hints.setdefault(text, _direction_from_delta(text_center[0] - shape_center[0], text_center[1] - shape_center[1]))
    return hints


def _center_from_evidence(obj: dict[str, Any]) -> tuple[float, float] | None:
    center = obj.get("center")
    if not isinstance(center, list) or len(center) < 2:
        return None
    try:
        return float(center[0]), float(center[1])
    except (TypeError, ValueError):
        return None


def _direction_from_delta(dx: float, dy: float) -> str:
    horizontal = "RIGHT" if dx >= 0 else "LEFT"
    vertical = "UP" if dy >= 0 else "DOWN"
    if abs(dx) >= 0.2 and abs(dy) >= 0.2:
        return {"UPRIGHT": "UR", "UPLEFT": "UL", "DOWNRIGHT": "DR", "DOWNLEFT": "DL"}[vertical + horizontal]
    if abs(dx) >= abs(dy):
        return horizontal
    return vertical


def _patch_point_label_callsite_directions(code: str, hints: dict[str, str]) -> tuple[str, bool]:
    patched = code
    for text, direction in hints.items():
        if not text or direction not in {"UP", "DOWN", "LEFT", "RIGHT", "UL", "UR", "DL", "DR"}:
            continue
        quoted = re.escape(text)
        patterns = (
            rf"((?:make_point_label|make_unknown_point_label|make_point_coord_label)\(\s*['\"]{quoted}['\"][^\n]*?direction\s*=\s*)[A-Z]+",
            rf"(reveal_point_coord\([^,\n]+,\s*['\"]{quoted}['\"][^\n]*?direction\s*=\s*)[A-Z]+",
        )
        for pattern in patterns:
            patched = re.sub(pattern, rf"\g<1>{direction}", patched)
    return patched, patched != code


def _short_label_text_overlap_direction_hints(brief: dict[str, Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for cluster in brief.get("clusters") if isinstance(brief.get("clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        for item in cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []:
            if not isinstance(item, dict) or str(item.get("category") or "") != "text_formula_overlap":
                continue
            raw_objects = item.get("objects")
            objects = [obj for obj in raw_objects if isinstance(obj, dict)] if isinstance(raw_objects, list) else []
            if len(objects) != 2:
                continue
            text_objects = [obj for obj in objects if obj.get("text")]
            if len(text_objects) != 2:
                continue
            moving = _short_non_coordinate_label(text_objects[0], text_objects[1])
            fixed = text_objects[1] if moving is text_objects[0] else text_objects[0] if moving is text_objects[1] else None
            if not moving or not fixed:
                continue
            moving_center = _center_from_evidence(moving)
            fixed_center = _center_from_evidence(fixed)
            if not moving_center or not fixed_center:
                continue
            direction = _direction_from_delta(moving_center[0] - fixed_center[0], moving_center[1] - fixed_center[1])
            for alias in _label_text_aliases(str(moving.get("text") or "")):
                hints.setdefault(alias, direction)
    return hints


def _short_label_texts_from_brief(brief: dict[str, Any]) -> set[str]:
    texts: set[str] = set()
    for cluster in brief.get("clusters") if isinstance(brief.get("clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        for item in cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []:
            if not isinstance(item, dict):
                continue
            raw_objects = item.get("objects")
            objects = [obj for obj in raw_objects if isinstance(obj, dict)] if isinstance(raw_objects, list) else []
            for obj in objects:
                text = str(obj.get("text") or "").strip()
                if _is_short_point_name(text) or _is_numbered_point_name(text):
                    texts.update(_label_text_aliases(text))
    return texts


def _short_non_coordinate_label(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [obj for obj in (a, b) if _is_short_point_name(str(obj.get("text") or ""))]
    if len(candidates) != 1:
        if len(candidates) == 2:
            return candidates[0]
        return None
    other = b if candidates[0] is a else a
    if _looks_like_coordinate_label(str(other.get("text") or "")):
        return candidates[0]
    return None


def _is_short_point_name(text: str) -> bool:
    compact = _normalize_label_text(text)
    return 1 <= len(compact) <= 3 and not _looks_like_coordinate_label(text)


def _is_numbered_point_name(text: str) -> bool:
    compact = _normalize_label_text(text)
    return bool(re.match(r"^[A-Za-z]\d+$", compact))


def _looks_like_coordinate_label(text: str) -> bool:
    return bool(re.search(r"\(-?\d+(?:\.\d+)?,\s*-?\d+(?:\.\d+)?\)", text.replace(" ", "")))


def _label_text_aliases(text: str) -> list[str]:
    aliases = [text]
    subscript_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    ascii_text = text.translate(subscript_map)
    if ascii_text != text:
        aliases.extend([ascii_text, re.sub(r"([A-Za-z])(\d+)$", r"\1_\2", ascii_text)])
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _normalize_label_text(text: str) -> str:
    return re.sub(r"[\s_{}()，,]", "", text.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")))


def _patch_short_label_obstacles_from_existing_labels(code: str, hints: dict[str, str]) -> tuple[str, bool]:
    target_texts = set(hints)
    if not target_texts:
        return code, False
    lines = code.splitlines(keepends=True)
    patched_lines: list[str] = []
    seen_labels: list[str] = []
    changed = False
    label_assign_re = re.compile(r"^\s*(?P<name>lbl_[A-Za-z0-9_]+)\s*=\s*self\.(?:make_point_label|make_unknown_point_label|make_point_coord_label)\(")
    obstacle_re = re.compile(r"(obstacles\s*=\s*\[)(?P<items>[^\]]*)(\])")
    for line in lines:
        if re.match(r"^\s*def\s+", line):
            seen_labels = []
        new_line = line
        if seen_labels and any(f'"{text}"' in line or f"'{text}'" in line for text in target_texts) and "obstacles=[" in line:
            excluded = set()
            assign_match = label_assign_re.match(line)
            if assign_match:
                excluded.add(assign_match.group("name"))
            reveal_match = re.search(r"reveal_point_coord\(\s*(lbl_[A-Za-z0-9_]+)\s*,", line)
            if reveal_match:
                excluded.add(reveal_match.group(1))
            candidates = [name for name in seen_labels[-6:] if name not in excluded]

            def replace_obstacles(match: re.Match[str]) -> str:
                nonlocal changed
                items = match.group("items")
                existing = [part.strip() for part in items.split(",") if part.strip()]
                additions = [name for name in candidates if name not in existing]
                if not additions:
                    return match.group(0)
                changed = True
                return f"{match.group(1)}{', '.join(existing + additions)}{match.group(3)}"

            new_line = obstacle_re.sub(replace_obstacles, line, count=1)
        patched_lines.append(new_line)
        assign_match = label_assign_re.match(new_line)
        if assign_match and assign_match.group("name") not in seen_labels:
            seen_labels.append(assign_match.group("name"))
        if "reset_to_axes(" in new_line:
            seen_labels = []
    return "".join(patched_lines), changed


def _patch_direct_text_label_directions(code: str, hints: dict[str, str]) -> tuple[str, bool]:
    target_texts = {text: direction for text, direction in hints.items() if _is_short_point_name(text)}
    if not target_texts:
        return code, False
    lines = code.splitlines(keepends=True)
    patched_lines: list[str] = []
    changed = False
    for line in lines:
        new_line = line
        for text, direction in target_texts.items():
            if direction not in {"UP", "DOWN", "LEFT", "RIGHT", "UL", "UR", "DL", "DR"}:
                continue
            if not (f'Text("{text}"' in new_line or f"Text('{text}'" in new_line):
                continue
            if ".next_to(" not in new_line:
                continue
            replaced = re.sub(r"(\.next_to\([^,\n]+,\s*)[^,\n]+", rf"\g<1>{direction}", new_line, count=1)
            replaced = re.sub(r"(buff\s*=\s*)0\.\d+", r"\g<1>0.55", replaced, count=1)
            if replaced != new_line:
                new_line = replaced
                changed = True
        patched_lines.append(new_line)
    return "".join(patched_lines), changed


def _patch_label_obstacles_from_existing_geometry(code: str) -> tuple[str, bool]:
    lines = code.splitlines(keepends=True)
    patched_lines: list[str] = []
    seen_geometry: list[str] = []
    changed = False
    assignment_re = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<rhs>.+)$")
    label_call_re = re.compile(
        r"(self\.(?:make_point_label|make_unknown_point_label|make_point_coord_label|reveal_point_coord)\([^\n]*?obstacles\s*=\s*\[)(?P<items>[^\]]*)(\])"
    )
    for line in lines:
        if re.match(r"^\s*def\s+", line):
            seen_geometry = []
        new_line = line
        if label_call_re.search(line) and seen_geometry:
            candidates = seen_geometry[-5:]

            def replace_obstacles(match: re.Match[str]) -> str:
                nonlocal changed
                items = match.group("items")
                existing = [part.strip() for part in items.split(",") if part.strip()]
                additions = [name for name in candidates if name not in existing]
                if not additions:
                    return match.group(0)
                changed = True
                merged = ", ".join(existing + additions)
                return f"{match.group(1)}{merged}{match.group(3)}"

            new_line = label_call_re.sub(replace_obstacles, line, count=1)
        patched_lines.append(new_line)
        match = assignment_re.match(new_line.strip("\n"))
        if match and not _is_likely_keyword_argument_assignment(match.group("name"), match.group("rhs")) and _is_geometry_assignment(match.group("name"), match.group("rhs")):
            name = match.group("name")
            if name not in seen_geometry:
                seen_geometry.append(name)
        if "reset_to_axes(" in new_line:
            seen_geometry = []
    return "".join(patched_lines), changed


def _patch_label_before_line_creation(code: str) -> tuple[str, bool]:
    pattern = re.compile(
        r"(?m)^(?P<indent>\s*)(?P<label>[A-Za-z_][A-Za-z0-9_]*\s*=\s*self\."
        r"(?:make_point_label|make_unknown_point_label|make_point_coord_label)\([^\n]*?obstacles\s*=\s*\[(?P<items>[^\]]*)\][^\n]*\))\n"
        r"(?P=indent)(?P<geom>(?P<geom_name>line_[A-Za-z0-9_]+)\s*=\s*(?:self\.make_line_by_formula\([^\n]*\)|Line\([^\n]*\)))"
    )

    def replacement(match: re.Match[str]) -> str:
        label = match.group("label")
        geom = match.group("geom")
        geom_name = match.group("geom_name")
        items = [part.strip() for part in match.group("items").split(",") if part.strip()]
        if geom_name not in items:
            label = re.sub(r"obstacles\s*=\s*\[[^\]]*\]", f"obstacles=[{', '.join(items + [geom_name])}]", label, count=1)
        indent = match.group("indent")
        return f"{indent}{geom}\n{indent}{label}"

    patched = pattern.sub(replacement, code)
    return patched, patched != code


def _is_geometry_assignment(name: str, rhs: str) -> bool:
    lowered = name.lower()
    if lowered.startswith(("line_", "area_", "circle_", "arc_", "poly_", "polygon_", "triangle_")):
        return True
    return any(token in rhs for token in ("Line(", "Arrow(", "Polygon(", "Circle(", "Arc(", "self.make_line_", "self.make_area_"))


def _is_likely_keyword_argument_assignment(name: str, rhs: str) -> bool:
    if name in {
        "arc_center",
        "start_angle",
        "angle",
        "radius",
        "color",
        "stroke_width",
        "fill_opacity",
        "font_size",
        "buff",
    }:
        return True
    return rhs.rstrip().endswith(",")


def _brief_has_text_bounds_overflow(brief: dict[str, Any]) -> bool:
    for cluster in brief.get("clusters") if isinstance(brief.get("clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        for item in cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []:
            if not isinstance(item, dict) or str(item.get("category") or "") != "frame_bounds_overflow":
                continue
            for obj in item.get("objects") if isinstance(item.get("objects"), list) else []:
                if not isinstance(obj, dict):
                    continue
                if str(obj.get("kind") or "") in {"text", "formula"} or str(obj.get("class") or "") in {"Text", "MathTex", "Tex"}:
                    return True
    return False


def _brief_has_text_container_overflow(brief: dict[str, Any]) -> bool:
    for cluster in brief.get("clusters") if isinstance(brief.get("clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        for item in cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []:
            if isinstance(item, dict) and str(item.get("category") or "") == "text_container_overflow":
                return True
    return False


def _brief_has_formula_stack_pressure(brief: dict[str, Any]) -> bool:
    categories: set[str] = set()
    classes: set[str] = set()
    for cluster in brief.get("clusters") if isinstance(brief.get("clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        for item in cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "")
            if category:
                categories.add(category)
            for obj in item.get("objects") if isinstance(item.get("objects"), list) else []:
                if isinstance(obj, dict) and obj.get("class"):
                    classes.add(str(obj.get("class")))
    return bool(
        {"text_formula_overlap", "frame_bounds_overflow"} & categories
        and {"MathTex", "Tex", "SingleStringMathTex"} & classes
    )


def _patch_formula_stack_compaction(code: str) -> tuple[str, bool]:
    patched = code
    targets = r"(?:rule_formula\d*|eq\d+|ans\d+)"
    pattern = re.compile(
        rf"(?P<prefix>\b{targets}\s*=\s*MathTex\((?:(?!font_size\s*=)[\s\S])*?)(?P<color>color\s*=)",
        re.MULTILINE,
    )
    patched = pattern.sub(r"\g<prefix>font_size=30, \g<color>", patched)
    return patched, patched != code


def _patch_mathtex_scale_font_size_misuse(code: str) -> tuple[str, bool]:
    patched = re.sub(
        r"MathTex\((?P<args>(?:(?!font_size\s*=)[^()\n])*)\)\.scale\(FS_LABEL\)",
        r"MathTex(\g<args>, font_size=GlobalConfig.FS_LABEL)",
        code,
    )
    patched = re.sub(
        r"MathTex\((?P<args>(?:(?!font_size\s*=)[^()\n])*)\)\.scale\(GlobalConfig\.FS_LABEL\)",
        r"MathTex(\g<args>, font_size=GlobalConfig.FS_LABEL)",
        patched,
    )
    return patched, patched != code


def _patch_formula_stack_board_lifecycle(code: str) -> tuple[str, bool]:
    if "self.formula_stack" not in code or "add_formula_line" not in code or "problem_panel" not in code:
        return code, False
    first_formula = re.search(
        r"(?m)^(?P<indent>\s*)[A-Za-z_][A-Za-z0-9_]*\s*,\s*anims\s*=\s*self\.add_formula_line\(",
        code,
    )
    if not first_formula:
        return code, False
    prefix = code[: first_formula.start()]
    if "FadeOut(problem_panel)" in prefix or "self.remove(problem_panel" in prefix:
        return code, False
    indent = first_formula.group("indent")
    insert = _panel_remove_line("problem_panel", indent)
    return code[: first_formula.start()] + insert + code[first_formula.start() :], True


def _patch_formula_stack_board_motion(code: str) -> tuple[str, bool]:
    if "self.formula_stack" not in code or "add_formula_line" not in code:
        return code, False
    patched = code
    patched = re.sub(r"(shift_up\s*=\s*UP\s*\*\s*)0\.7\b", r"\g<1>0.65", patched)
    patched = re.sub(r"(self\.max_stack_size\s*=\s*)5\b", r"\g<1>4", patched)
    patched = re.sub(
        r"(new_line\.move_to\(\s*LEFT\s*\*\s*2\s*\+\s*UP\s*\*\s*)0\.5(\s*\))",
        r"\g<1>0.2\2",
        patched,
    )
    patched = re.sub(
        r"""(?ms)(?P<indent>\s*)else:\n"""
        r"""(?P=indent)    new_line\.next_to\(self\.formula_stack\[-1\], DOWN, buff=0\.3\)\n"""
        r"""(?P=indent)    if align_left:\n"""
        r"""(?P=indent)        new_line\.align_to\(self\.formula_stack\[-1\], LEFT\)\n"""
        r"""(?P=indent)    else:\n"""
        r"""(?P=indent)        new_line\.shift\(RIGHT \* 0\.5\)""",
        r"""\g<indent>else:
\g<indent>    new_line.move_to(LEFT * 2 + DOWN * 1.2)
\g<indent>    if align_left:
\g<indent>        new_line.align_to(self.formula_stack[-1], LEFT)
\g<indent>    else:
\g<indent>        new_line.shift(RIGHT * 0.5)""",
        patched,
        count=1,
    )
    patched = re.sub(r"(move_to\([^\n]*?\+\s*UP\s*\*\s*)1\.5(\s*\))", r"\g<1>0.8\2", patched)
    return patched, patched != code


def _patch_right_panel_formula_lifecycle(code: str) -> tuple[str, bool]:
    formula_vars = set(re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*self\.make_formula\(", code))
    if not formula_vars:
        return code, False
    anchor_by_var: dict[str, str] = {}
    previous_formula_by_var: dict[str, str] = {}
    panel_index_by_var: dict[str, tuple[str, int]] = {}

    def replace_next_to(match: re.Match[str]) -> str:
        var = match.group("var")
        anchor = match.group("anchor").strip()
        resolved_anchor = anchor
        if anchor in anchor_by_var:
            resolved_anchor = anchor_by_var[anchor]
            previous_formula_by_var[var] = anchor
        anchor_by_var[var] = resolved_anchor
        panel_match = re.search(r"\b(?P<panel>step_panel_[A-Za-z0-9_]+)\[(?P<idx>\d+)\]", resolved_anchor)
        if panel_match:
            panel_index_by_var[var] = (panel_match.group("panel"), int(panel_match.group("idx")))
        if resolved_anchor == anchor:
            return match.group(0)
        return f"{match.group('indent')}{var}.next_to({resolved_anchor}, DOWN, aligned_edge=LEFT)"

    next_to_pattern = re.compile(
        r"(?m)^(?P<indent>\s*)(?P<var>[A-Za-z_][A-Za-z0-9_]*)\.next_to\((?P<anchor>[^,\n]+), DOWN, aligned_edge=LEFT\)"
    )
    patched = next_to_pattern.sub(replace_next_to, code)

    for var, previous in previous_formula_by_var.items():
        patched = _prepend_animation_in_play_list(patched, f"FadeIn({var})", f"FadeOut({previous})")

    formula_positions = {var: patched.find(f"{var} = self.make_formula(") for var in formula_vars}

    def replace_step_write(match: re.Match[str]) -> str:
        panel = match.group("panel")
        idx = int(match.group("idx"))
        line = match.group(0)
        additions = []
        for var, panel_index in panel_index_by_var.items():
            if panel_index[0] != panel or panel_index[1] >= idx:
                continue
            position = formula_positions.get(var, -1)
            if position < 0 or position > match.start():
                continue
            if f"FadeOut({var})" not in line:
                additions.append(f"FadeOut({var})")
        if not additions:
            return line
        return line.replace("[", "[" + ", ".join(additions) + ", ", 1)

    step_write_pattern = re.compile(
        r"(?m)^.*self\.play_steps_evenly\(\[.*Write\((?P<panel>step_panel_[A-Za-z0-9_]+)\[(?P<idx>\d+)\].*$"
    )
    patched = step_write_pattern.sub(replace_step_write, patched)
    return patched, patched != code


def _patch_option_analysis_table_spacing(code: str) -> tuple[str, bool]:
    if not all(token in code for token in ("col1_x", "col2_x", "col3_x")):
        return code, False
    patched = code
    patched = re.sub(r"(?m)^(\s*col2_x\s*=\s*)-?\d+(?:\.\d+)?\b", r"\g<1>-3.25", patched, count=1)
    patched = re.sub(r"(?m)^(\s*col3_x\s*=\s*)-?\d+(?:\.\d+)?\b", r"\g<1>0.65", patched, count=1)
    patched = re.sub(r"(_det\s*=\s*MathTex\([^\n]+?\)\.scale\()0\.7(\)\.move_to)", r"\g<1>0.58\2", patched)
    patched = re.sub(r"(_res\s*=\s*MathTex\([^\n]+?\)\.scale\()0\.8(\)\.move_to)", r"\g<1>0.68\2", patched)
    patched = re.sub(
        r"(?m)^(\s*)(ans_panel\s*=\s*VGroup\(\*ans_lines\)\.arrange\([^\n]+\)\n)\1(ans_panel\.move_to\()",
        r"\1\2\1if ans_panel.width > 5.7:\n\1    ans_panel.scale_to_fit_width(5.7)\n\1if ans_panel.height > 3.1:\n\1    ans_panel.scale_to_fit_height(3.1)\n\1\3",
        patched,
        count=1,
    )
    return patched, patched != code


def _patch_local_formula_stack_spacing(code: str) -> tuple[str, bool]:
    if "def add_formula" not in code or "formula_stack" not in code:
        return code, False
    patched = code
    patched = re.sub(
        r"(new_line\.move_to\(left_center \+ UP \* )1\.5(\))",
        r"\g<1>0.7\2",
        patched,
        count=1,
    )
    patched = re.sub(r"(new_line\s*=\s*MathTex\([^\n]*?font_size\s*=\s*)36\b", r"\g<1>32", patched, count=1)
    patched = re.sub(
        r"new_line\.next_to\(formula_stack\[-1\], DOWN, buff\s*=\s*0\.4, aligned_edge=LEFT\)",
        "new_line.move_to(left_center + UP * 0.7)",
        patched,
        count=1,
    )
    patched = re.sub(
        r"(?ms)(?P<indent>\s*)anims = \[Write\(new_line\)\]\n"
        r"(?P=indent)if highlight_prev_gray and len\(formula_stack\) > 0:\n"
        r"(?P=indent)    anims\.append\(formula_stack\[-1\]\.animate\.set_color\(TEXT_COLOR\)\)",
        r"\g<indent>if highlight_prev_gray and len(formula_stack) > 0:\n"
        r"\g<indent>    self.play_steps_evenly([FadeOut(formula_stack[-1])], tracker)\n"
        r"\g<indent>anims = [Write(new_line)]",
        patched,
        count=1,
    )
    patched = re.sub(r"(if len\(formula_stack\) >= )5\b", r"\g<1>999", patched, count=1)
    patched = re.sub(r"(formula_stack\[i\]\.animate\.shift\(UP \* )0\.8(\))", r"\g<1>1.15\2", patched, count=1)
    patched = re.sub(
        r"formula_stack\[-1\]\.animate\.move_to\(left_center \+ UP \* 2\.2\)\.set_color\(KNOWN_COLOR\)\.set_font_size\(28\)",
        r"FadeOut(formula_stack[-1])",
        patched,
        count=1,
    )
    patched = patched.replace("formula_stack = VGroup(formula_stack[-1])", "formula_stack = VGroup()", 1)
    return patched, patched != code


def _patch_right_rule_condition_spacing(code: str) -> tuple[str, bool]:
    if "rule_steps" not in code or "cond_group" not in code:
        return code, False
    patched = code
    patched = re.sub(
        r"(rule_steps\s*=\s*VGroup\([^\n]+?\)\.arrange\(DOWN,\s*aligned_edge=LEFT,\s*buff=)0\.15(\))",
        r"\g<1>0.08\2",
        patched,
        count=1,
    )
    patched = re.sub(
        r"(rule_steps\.next_to\(rule_area,\s*DOWN,\s*buff=)0\.4(,\s*aligned_edge=LEFT\))",
        r"\g<1>0.2\2",
        patched,
        count=1,
    )
    patched = re.sub(
        r"(cond_group[12]?\s*=\s*VGroup\([^\n]+?\)\.arrange\(DOWN,\s*aligned_edge=LEFT,\s*buff=)0\.15(\))",
        r"\g<1>0.10\2",
        patched,
    )
    patched = re.sub(
        r"(cond_group[12]?\.move_to\(RIGHT \* 3\.5 \+ DOWN \* )1\.2(\))",
        r"\g<1>1.6\2",
        patched,
    )
    return patched, patched != code


def _patch_summary_panel_fades_step_formulas(code: str) -> tuple[str, bool]:
    if "方法总结" not in code or "step3" not in code:
        return code, False
    original = code
    patched = re.sub(
        r"self\.play\(FadeOut\(s1\),\s*FadeOut\(s2\),\s*FadeOut\(s3\)\)",
        "self.play(*[FadeOut(mob) for group in (s1, s2, s3) for mob in group])",
        code,
        count=1,
    )
    pattern = re.compile(r"(?m)^(?P<indent>\s*)tip_panel\s*=\s*self\.make_step_panel\(\[")
    code = patched
    match = pattern.search(code)
    if not match:
        return code, code != original
    prefix = code[max(0, match.start() - 300) : match.start()]
    if "for group in (s1, s2, s3, step1, step2, step3)" in prefix:
        return code, code != original
    names = [name for name in ("s1", "s2", "s3", "step1", "step2", "step3", "sol_text") if re.search(rf"(?m)^\s*{name}\s*=", code[: match.start()])]
    if not names:
        return code, code != original
    indent = match.group("indent")
    grouped = [name for name in names if name != "sol_text"]
    extra = ", FadeOut(sol_text)" if "sol_text" in names else ""
    if grouped:
        group_expr = ", ".join(grouped)
        if len(grouped) == 1:
            group_expr += ","
        insert = (
            f"{indent}self.play(*[FadeOut(mob) for group in ({group_expr}) "
            f"for mob in group]{extra})\n"
        )
    else:
        insert = f"{indent}self.play(FadeOut(sol_text))\n"
    return code[: match.start()] + insert + code[match.start() :], True


def _prepend_animation_in_play_list(code: str, marker: str, insertion: str) -> str:
    pattern = re.compile(rf"(?m)^(?P<line>.*self\.play_steps_evenly\(\[(?P<body>[^\n]*{re.escape(marker)}[^\n]*)\].*)$")

    def replace(match: re.Match[str]) -> str:
        line = match.group("line")
        if insertion in line:
            return line
        return line.replace("[", f"[{insertion}, ", 1)

    return pattern.sub(replace, code)


def _patch_problem_panel_fade_before_first_step(code: str) -> tuple[str, bool]:
    if "problem_panel = self.make_problem_panel" not in code:
        return code, False
    step_panel_names = _step_panel_variable_names(code)
    if not step_panel_names:
        return code, False
    first_step_match = _first_place_panel_match(code, step_panel_names)
    if not first_step_match:
        return code, False
    prefix = code[: first_step_match.start()]
    if "FadeOut(problem_panel)" in prefix or "self.remove(problem_panel" in prefix:
        return code, False
    indent = first_step_match.group("indent")
    insert = _panel_remove_line("problem_panel", indent)
    return code[: first_step_match.start()] + insert + code[first_step_match.start() :], True


def _patch_step_panel_sequence_fade_previous(code: str) -> tuple[str, bool]:
    step_panel_names = _step_panel_variable_names(code)
    if not step_panel_names:
        return code, False
    matches = [
        match
        for match in re.finditer(r"(?m)^(?P<indent>\s*)self\.place_panel\((?P<name>[A-Za-z_][A-Za-z0-9_]*)\)", code)
        if match.group("name") in step_panel_names
    ]
    if len(matches) < 2:
        return code, False
    pieces: list[str] = []
    cursor = 0
    previous_name: str | None = None
    previous_end = 0
    changed = False
    for match in matches:
        if previous_name is not None:
            between = code[previous_end : match.start()]
            if f"FadeOut({previous_name})" not in between and f"self.remove({previous_name}" not in between:
                pieces.append(code[cursor : match.start()])
                pieces.append(_panel_remove_line(previous_name, match.group("indent")))
                cursor = match.start()
                changed = True
        previous_name = match.group("name")
        previous_end = match.end()
    if not changed:
        return code, False
    pieces.append(code[cursor:])
    return "".join(pieces), True


def _panel_remove_line(name: str, indent: str) -> str:
    return f'{indent}self.remove({name}, *getattr({name}, "submobjects", []))\n'


def _step_panel_variable_names(code: str) -> set[str]:
    names = set(re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*self\.make_step_panel\(", code))
    names.update(re.findall(r"(?m)^\s*(step_panel_[A-Za-z0-9_]+)\s*=", code))
    return names


def _first_place_panel_match(code: str, names: set[str]) -> re.Match[str] | None:
    for match in re.finditer(r"(?m)^(?P<indent>\s*)self\.place_panel\((?P<name>[A-Za-z_][A-Za-z0-9_]*)\)", code):
        if match.group("name") in names:
            return match
    return None
