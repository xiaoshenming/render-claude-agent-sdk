from __future__ import annotations

import csv
import io
import json
import random
import re
import shutil
import tokenize
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "logic_engine_mvp.mutation_eval.v1"
DEFAULT_DIFFICULTIES = ("medium", "hard", "expert")


@dataclass(frozen=True)
class MutationCandidate:
    rule_id: str
    issue_type: str
    difficulty: str
    line_no: int
    original_text: str
    mutated_text: str
    expected_fix: str
    rationale: str


@dataclass(frozen=True)
class MutationResult:
    code: str
    candidate: MutationCandidate
    ground_truth: dict[str, Any]


def build_mutation_candidates(code_text: str) -> list[MutationCandidate]:
    """Find render-preserving math/logic mutations in visible text and drawn geometry."""
    candidates: list[MutationCandidate] = []
    point_names = _geometry_point_names(code_text)
    for line_no, line in enumerate(code_text.splitlines(), start=1):
        candidates.extend(_point_coordinate_shift(line_no, line))
        candidates.extend(_axes_point_shift(line_no, line))
        candidates.extend(_line_endpoint_swap(line_no, line, point_names))

        stripped = line.strip()
        if not _looks_like_visible_claim(stripped):
            continue
        candidates.extend(_undefined_angle_endpoint(line_no, line))
        candidates.extend(_line_relation_swap(line_no, line))
        candidates.extend(_chinese_line_relation_swap(line_no, line))
        candidates.extend(_equality_to_inequality(line_no, line))
        candidates.extend(_ratio_factor_error(line_no, line))
        candidates.extend(_word_factor_error(line_no, line))
        candidates.extend(_midpoint_condition_error(line_no, line))
        candidates.extend(_theorem_concept_swap(line_no, line))
        candidates.extend(_circle_line_type_swap(line_no, line))
        candidates.extend(_proof_method_swap(line_no, line))
    return _dedupe_candidates(candidates)


def mutate_code(
    code_text: str,
    *,
    seed: int = 0,
    allowed_difficulties: Sequence[str] = DEFAULT_DIFFICULTIES,
) -> MutationResult:
    candidates = [
        candidate
        for candidate in build_mutation_candidates(code_text)
        if candidate.difficulty in set(allowed_difficulties)
    ]
    if not candidates:
        raise ValueError("no mutation candidate found for the requested difficulties")
    rng = random.Random(seed)
    candidate = rng.choice(candidates)
    return _mutate_code_with_candidate(code_text, candidate)


def _mutate_code_with_candidate(code_text: str, candidate: MutationCandidate) -> MutationResult:
    lines = code_text.splitlines()
    index = candidate.line_no - 1
    if index < 0 or index >= len(lines):
        raise ValueError(f"candidate line out of range: {candidate.line_no}")
    if lines[index] != candidate.original_text:
        raise ValueError("candidate source line no longer matches original text")
    lines[index] = candidate.mutated_text
    mutated_code = "\n".join(lines)
    if code_text.endswith("\n"):
        mutated_code += "\n"
    return MutationResult(
        code=mutated_code,
        candidate=candidate,
        ground_truth={
            "schema_version": SCHEMA_VERSION,
            "mutation_type": candidate.rule_id,
            "issue_type": candidate.issue_type,
            "difficulty": candidate.difficulty,
            "line_no": candidate.line_no,
            "original_text": candidate.original_text,
            "mutated_text": candidate.mutated_text,
            "expected_fix": candidate.expected_fix,
            "rationale": candidate.rationale,
            "verification_policy": {
                "reviewer_should_detect": True,
                "agent_should_restore_original_or_equivalent": True,
                "must_render_after_repair": True,
                "avoid_full_rewrite": True,
            },
        },
    )


def generate_mutation_pack(
    source_samples_root: Path,
    out_root: Path,
    *,
    limit: int | None = None,
    seed: int = 0,
    allowed_difficulties: Sequence[str] = DEFAULT_DIFFICULTIES,
    variants_per_source: int = 1,
) -> dict[str, Any]:
    source_samples_root = _resolve_samples_root(Path(source_samples_root))
    out_root = Path(out_root)
    samples_out = out_root / "samples"
    samples_out.mkdir(parents=True, exist_ok=True)
    source_samples = [
        sample_dir
        for sample_dir in sorted(source_samples_root.iterdir())
        if sample_dir.is_dir() and (sample_dir / "candidate.py").exists()
    ]
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    rng = random.Random(seed)
    candidate_queues: list[tuple[Path, list[MutationCandidate]]] = []
    for sample_dir in source_samples:
        code = (sample_dir / "candidate.py").read_text(encoding="utf-8", errors="replace")
        candidates = [
            candidate
            for candidate in build_mutation_candidates(code)
            if candidate.difficulty in set(allowed_difficulties)
        ]
        if not candidates:
            skipped.append(
                {
                    "sample_id": sample_dir.name,
                    "reason": "no mutation candidate found for the requested difficulties",
                }
            )
            continue
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        candidate_queues.append((sample_dir, shuffled[: max(1, variants_per_source)]))

    while limit is None or len(created) < limit:
        made_progress = False
        for sample_dir, queue in candidate_queues:
            if limit is not None and len(created) >= limit:
                break
            if not queue:
                continue
            made_progress = True
            candidate = queue.pop(0)
            code = (sample_dir / "candidate.py").read_text(encoding="utf-8", errors="replace")
            result = _mutate_code_with_candidate(code, candidate)
            sample_id = _short_mutation_sample_id(len(created) + 1, result.candidate)
            dest = samples_out / sample_id
            dest.mkdir(parents=True, exist_ok=True)
            _write_mutated_sample(sample_dir, dest, sample_id, result)
            created.append(
                {
                    "sample_id": sample_id,
                    "source_sample_id": sample_dir.name,
                    "mutation_type": result.candidate.rule_id,
                    "issue_type": result.candidate.issue_type,
                    "difficulty": result.candidate.difficulty,
                    "line_no": result.candidate.line_no,
                    "candidate": str(dest / "candidate.py"),
                    "ground_truth": str(dest / "mutation_ground_truth.json"),
                    "problem_preview": _read_question(dest)[:240],
                }
            )
        if not made_progress:
            break

    summary = {
        "schema_version": SCHEMA_VERSION,
        "pack_id": out_root.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_samples_root": str(source_samples_root),
        "out_root": str(out_root),
        "sample_count": len(created),
        "skipped_count": len(skipped),
        "allowed_difficulties": list(allowed_difficulties),
        "variants_per_source": variants_per_source,
        "samples": created,
        "skipped": skipped,
    }
    _write_json(out_root / "manifest.json", summary)
    _write_manifest_csv(out_root / "manifest.csv", created)
    return summary


def _looks_like_visible_claim(line: str) -> bool:
    if not line or line.startswith("#"):
        return False
    constructors = ("Text(", "Tex(", "MathTex(", "MarkupText(")
    return any(name in line for name in constructors)


def _geometry_point_names(code_text: str) -> list[str]:
    names: list[str] = []
    for line in code_text.splitlines():
        match = re.match(r"\s*([A-Z][A-Za-z0-9_]*)\s*=\s*(?:np\.array|ORIGIN\b|[A-Za-z_][A-Za-z0-9_]*\s*\+)", line)
        if not match:
            continue
        name = match.group(1)
        if name == "O":
            continue
        if name not in names:
            names.append(name)
    return names


def _point_coordinate_shift(line_no: int, line: str) -> Iterable[MutationCandidate]:
    match = re.match(
        r"^(\s*([A-Z][A-Za-z0-9_]*)\s*=\s*np\.array\(\[\s*)"
        r"(-?\d+(?:\.\d+)?)"
        r"(\s*,\s*)"
        r"(-?\d+(?:\.\d+)?)"
        r"(\s*,\s*)"
        r"(-?\d+(?:\.\d+)?)"
        r"(\s*\]\).*)$",
        line,
    )
    if not match:
        return []
    point_name = match.group(2)
    if point_name == "O":
        return []
    x_value = float(match.group(3))
    y_value = float(match.group(5))
    z_value = float(match.group(7))
    if abs(z_value) > 1e-9:
        return []
    if abs(y_value) >= 0.2:
        new_x = x_value
        new_y = y_value + 0.8 if y_value < 0 else y_value - 0.8
    else:
        new_x = x_value + 0.8 if x_value >= 0 else x_value - 0.8
        new_y = y_value
    mutated = (
        f"{match.group(1)}{_format_number(new_x)}{match.group(4)}"
        f"{_format_number(new_y)}{match.group(6)}{match.group(7)}{match.group(8)}"
    )
    if mutated == line:
        return []
    return [
        _candidate(
            "point_coordinate_shift",
            "wrong_geometry_position",
            "expert",
            line_no,
            line,
            mutated,
            line,
            "A defined geometry point coordinate is shifted, so the rendered construction is in the wrong position.",
        )
    ]


def _axes_point_shift(line_no: int, line: str) -> Iterable[MutationCandidate]:
    match = re.search(
        r"(axes\.c2p\(\s*)"
        r"(-?\d+(?:\.\d+)?)"
        r"(\s*,\s*)"
        r"(-?\d+(?:\.\d+)?)"
        r"(\s*\))",
        line,
    )
    if not match:
        return []
    x_value = float(match.group(2))
    y_value = float(match.group(4))
    new_x = x_value + 1 if x_value >= 0 else x_value - 1
    mutated_call = (
        f"{match.group(1)}{_format_number(new_x)}{match.group(3)}"
        f"{_format_number(y_value)}{match.group(5)}"
    )
    mutated = line[: match.start()] + mutated_call + line[match.end() :]
    return [
        _candidate(
            "axes_point_shift",
            "wrong_graph_coordinate",
            "expert",
            line_no,
            line,
            mutated,
            line,
            "A graph point is plotted at a nearby but mathematically wrong coordinate.",
        )
    ]


def _line_endpoint_swap(line_no: int, line: str, point_names: Sequence[str]) -> Iterable[MutationCandidate]:
    match = re.search(
        r"(\b(?:Line|DashedLine|Arrow|DoubleArrow)\(\s*)"
        r"([A-Z][A-Za-z0-9_]*)"
        r"(\s*,\s*)"
        r"([A-Z][A-Za-z0-9_]*)"
        r"(\b)",
        line,
    )
    if not match:
        return []
    start_name = match.group(2)
    end_name = match.group(4)
    replacement = next((name for name in point_names if name not in {start_name, end_name}), None)
    if replacement is None:
        return []
    mutated = (
        line[: match.start()]
        + f"{match.group(1)}{start_name}{match.group(3)}{replacement}{match.group(5)}"
        + line[match.end() :]
    )
    return [
        _candidate(
            "line_endpoint_swap",
            "wrong_geometry_endpoint",
            "expert",
            line_no,
            line,
            mutated,
            line,
            "A drawn line keeps rendering but connects to the wrong defined geometry point.",
        )
    ]


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _undefined_angle_endpoint(line_no: int, line: str) -> Iterable[MutationCandidate]:
    # Example: \angle OAl -> \angle OAQ. This keeps LaTeX renderable but creates an undefined point.
    match = re.search(r"\\angle\s+([A-Z]{2})([a-z])\b", line)
    if not match:
        return []
    original = match.group(0)
    mutated = f"\\angle {match.group(1)}Q"
    return [
        _candidate(
            "undefined_angle_endpoint",
            "wrong_angle_label",
            "medium",
            line_no,
            line,
            line.replace(original, mutated, 1),
            "Replace the undefined angle endpoint with the original defined line/ray label.",
            "A lowercase line/ray label inside an angle is replaced with an undefined uppercase point.",
        )
    ]


def _line_relation_swap(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "\\parallel" in line:
        return [
            _candidate(
                "line_relation_swap",
                "wrong_line_relation",
                "medium",
                line_no,
                line,
                line.replace("\\parallel", "\\perp", 1),
                line,
                "A parallel relation is changed to perpendicular while preserving renderability.",
            )
        ]
    if "\\perp" in line and "90" not in line:
        return [
            _candidate(
                "line_relation_swap",
                "wrong_line_relation",
                "medium",
                line_no,
                line,
                line.replace("\\perp", "\\parallel", 1),
                line,
                "A perpendicular relation is changed to parallel while preserving renderability.",
            )
        ]
    return []


def _chinese_line_relation_swap(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "平行" in line:
        return [
            _candidate(
                "chinese_line_relation_swap",
                "wrong_line_relation",
                "medium",
                line_no,
                line,
                line.replace("平行", "垂直", 1),
                line,
                "A Chinese visible statement changes a parallel relation into perpendicular.",
            )
        ]
    if "垂直" in line:
        return [
            _candidate(
                "chinese_line_relation_swap",
                "wrong_line_relation",
                "medium",
                line_no,
                line,
                line.replace("垂直", "平行", 1),
                line,
                "A Chinese visible statement changes a perpendicular relation into parallel.",
            )
        ]
    return []


def _equality_to_inequality(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "\\ne" in line or "\\neq" in line:
        return []
    mutated = _replace_first_string_regex(
        line,
        r"(?<![<>=!])\s=\s(?![=>])",
        r" \\ne ",
    )
    if mutated is None:
        return []
    if not re.search(r"[A-Z][A-Z]?\s*\\ne\s*[A-Z][A-Z]?", mutated):
        return []
    return [
        _candidate(
            "equality_inequality_flip",
            "wrong_equal_relation",
            "medium",
            line_no,
            line,
            mutated,
            line,
            "A true equality claim is flipped into an inequality claim.",
        )
    ]


def _ratio_factor_error(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "\\frac{1}{2}" not in line:
        return []
    return [
        _candidate(
            "ratio_factor_error",
            "wrong_ratio_or_factor",
            "hard",
            line_no,
            line,
            line.replace("\\frac{1}{2}", "\\frac{2}{1}", 1),
            line,
            "A half-angle or midpoint factor is inverted into a doubled factor.",
        )
    ]


def _word_factor_error(line_no: int, line: str) -> Iterable[MutationCandidate]:
    replacements = (("一半", "两倍"), ("二分之一", "二倍"), ("1/2", "2"))
    for before, after in replacements:
        if before in line:
            return [
                _candidate(
                    "word_factor_error",
                    "wrong_ratio_or_factor",
                    "hard",
                    line_no,
                    line,
                    line.replace(before, after, 1),
                    line,
                    "A Chinese visible factor statement changes half into double.",
                )
            ]
    return []


def _midpoint_condition_error(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "中点" not in line:
        return []
    return [
        _candidate(
            "midpoint_condition_error",
            "wrong_geometry_condition",
            "hard",
            line_no,
            line,
            line.replace("中点", "任意点", 1),
            line,
            "A midpoint condition is weakened to an arbitrary-point condition.",
        )
    ]


def _theorem_concept_swap(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "全等" in line:
        return [
            _candidate(
                "theorem_concept_swap",
                "wrong_theorem_concept",
                "hard",
                line_no,
                line,
                line.replace("全等", "相似", 1),
                line,
                "A congruence theorem claim is swapped into a similarity claim.",
            )
        ]
    if "相似" in line:
        return [
            _candidate(
                "theorem_concept_swap",
                "wrong_theorem_concept",
                "hard",
                line_no,
                line,
                line.replace("相似", "全等", 1),
                line,
                "A similarity theorem claim is swapped into a congruence claim.",
            )
        ]
    return []


def _circle_line_type_swap(line_no: int, line: str) -> Iterable[MutationCandidate]:
    if "切线" not in line:
        return []
    return [
        _candidate(
            "circle_line_type_swap",
            "wrong_geometry_object_type",
            "expert",
            line_no,
            line,
            line.replace("切线", "割线", 1),
            line,
            "A circle tangent statement is changed into a secant statement.",
        )
    ]


def _proof_method_swap(line_no: int, line: str) -> Iterable[MutationCandidate]:
    swaps = (("SAS", "SSS"), ("SSS", "SAS"), ("HL", "SAS"), ("ASA", "SAS"))
    for before, after in swaps:
        if before in line:
            return [
                _candidate(
                    "proof_method_mismatch",
                    "wrong_proof_criterion",
                    "hard",
                    line_no,
                    line,
                    line.replace(before, after, 1),
                    line,
                    "A proof criterion label is changed while the surrounding reasoning stays the same.",
                )
            ]
    return []


def _replace_first_string_regex(line: str, pattern: str, replacement: str) -> str | None:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(line + "\n").readline)
        for token in tokens:
            if token.type != tokenize.STRING:
                continue
            start = token.start[1]
            end = token.end[1]
            token_text = line[start:end]
            mutated_token = re.sub(pattern, replacement, token_text, count=1)
            if mutated_token != token_text:
                return line[:start] + mutated_token + line[end:]
    except tokenize.TokenError:
        return None
    return None


def _candidate(
    rule_id: str,
    issue_type: str,
    difficulty: str,
    line_no: int,
    original: str,
    mutated: str,
    expected_fix: str,
    rationale: str,
) -> MutationCandidate:
    return MutationCandidate(
        rule_id=rule_id,
        issue_type=issue_type,
        difficulty=difficulty,
        line_no=line_no,
        original_text=original,
        mutated_text=mutated,
        expected_fix=expected_fix,
        rationale=rationale,
    )


def _dedupe_candidates(candidates: list[MutationCandidate]) -> list[MutationCandidate]:
    seen = set()
    unique: list[MutationCandidate] = []
    for candidate in candidates:
        key = (candidate.rule_id, candidate.line_no, candidate.original_text, candidate.mutated_text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _resolve_samples_root(path: Path) -> Path:
    nested = path / "samples"
    if nested.exists() and nested.is_dir():
        return nested
    return path


def _short_mutation_sample_id(index: int, candidate: MutationCandidate) -> str:
    rule = re.sub(r"[^A-Za-z0-9_]+", "_", candidate.rule_id).strip("_")
    value = f"MUT{index:03d}_{candidate.difficulty}_{rule}"
    return value[:64]


def _write_mutated_sample(
    source: Path,
    dest: Path,
    sample_id: str,
    result: MutationResult,
) -> None:
    (dest / "candidate.py").write_text(result.code, encoding="utf-8")
    shutil.copy2(source / "candidate.py", dest / "original_candidate.py")
    for name in ("problem_text.txt", "question.txt", "problem.md"):
        _copy_optional(source / name, dest / name)
    if not any((dest / name).exists() for name in ("problem_text.txt", "question.txt", "problem.md")):
        (dest / "problem_text.txt").write_text("", encoding="utf-8")
    _copy_optional(source / "before.mp4", dest / "source_correct.mp4")

    truth = {
        **result.ground_truth,
        "sample_id": sample_id,
        "source_sample_id": source.name,
        "source_candidate": str(source / "candidate.py"),
    }
    _write_json(dest / "mutation_ground_truth.json", truth)

    meta = _read_json_object(source / "sample_meta.json")
    meta.update(
        {
            "case_id": sample_id,
            "source_sample_id": source.name,
            "mutation_eval": True,
            "mutation_type": result.candidate.rule_id,
            "difficulty": result.candidate.difficulty,
            "error_type": result.candidate.issue_type,
            "visible_error_description": result.candidate.rationale,
            "expected_outcome": result.candidate.expected_fix,
            "repair_policy": "restore original or equivalent correct math claim; keep renderable; avoid full rewrite",
        }
    )
    _write_json(dest / "sample_meta.json", meta)
    _write_json(
        dest / "case_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": sample_id,
            "source_sample_id": source.name,
            "category": "mutation_logic_eval",
            "error_type": result.candidate.issue_type,
            "repair_policy": "mutation_eval_restore_original_or_equivalent",
            "visible_error_description": result.candidate.rationale,
            "expected_visual_change": "Correct the injected math/logic claim only.",
            "expected_outcome": result.candidate.expected_fix,
            "contracts": [
                {
                    "mutation_type": result.candidate.rule_id,
                    "difficulty": result.candidate.difficulty,
                    "line_no": result.candidate.line_no,
                    "wrong_text": result.candidate.mutated_text,
                    "expected_text": result.candidate.expected_fix,
                }
            ],
        },
    )
    (dest / "source_info.txt").write_text(
        "\n".join(
            [
                "source=mutation_eval",
                f"source_sample_id={source.name}",
                f"mutation_type={result.candidate.rule_id}",
                f"difficulty={result.candidate.difficulty}",
                f"line_no={result.candidate.line_no}",
            ]
        ),
        encoding="utf-8",
    )


def _copy_optional(src: Path, dest: Path) -> None:
    if src.exists():
        shutil.copy2(src, dest)


def _read_question(sample_dir: Path) -> str:
    for name in ("problem_text.txt", "question.txt", "problem.md"):
        path = sample_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_manifest_csv(path: Path, samples: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "sample_id",
        "source_sample_id",
        "mutation_type",
        "issue_type",
        "difficulty",
        "line_no",
        "candidate",
        "ground_truth",
        "problem_preview",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            writer.writerow({field: sample.get(field, "") for field in fields})
