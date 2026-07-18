from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from .logic_facts import extract_deterministic_logic_facts


MAX_CODE_CHARS = 8_000
MAX_FOCUSED_EXCERPT_CHARS = 40_000
MAX_HELPER_METHOD_EXCERPTS = 18
MAX_EVIDENCE_FOCUSED_EXCERPTS = 6
MAX_EVIDENCE_FOCUSED_EXCERPT_CHARS = 1_800
MAX_VISIBLE_MATH_CLAIMS = 120
MAX_VISIBLE_MATH_CLAIM_CHARS = 260
EVIDENCE_FOCUSED_WINDOW_LINES = 3
ORCHESTRATION_HELPERS = {"voiceover", "wait", "clear"}
ORCHESTRATION_PREFIXES = ("play", "wait", "normalize", "_tts")
LOGIC_HELPER_PREFIXES = (
    "make_",
    "create_",
    "draw_",
    "plot_",
    "calc_",
    "compute_",
    "get_",
    "build_",
    "label_",
    "highlight_",
)
LOGIC_HELPER_KEYWORDS = (
    "point",
    "line",
    "axis",
    "axes",
    "angle",
    "circle",
    "triangle",
    "polygon",
    "coord",
    "formula",
    "tex",
    "math",
    "label",
    "highlight",
)
CURRENT_SAMPLE_EVIDENCE_KEYS = (
    "case_id",
    "scene_name",
    "error_type",
    "category",
    "repair_policy",
    "visible_error_description",
    "expected_visual_change",
    "expected_outcome",
)
VISIBLE_MATH_KEYWORDS = (
    "题",
    "求",
    "解",
    "已知",
    "则",
    "答案",
    "结论",
    "证明",
    "因为",
    "所以",
    "等于",
    "角",
    "边",
    "底角",
    "周长",
    "面积",
    "半径",
    "直径",
    "坐标",
    "斜率",
    "方程",
    "相似",
    "全等",
    "平行",
    "垂直",
    "中点",
    "对称",
    "折叠",
    "根式",
    "二次",
    "三角",
    "四边形",
    "圆",
    "线段",
    "交于",
)
VISIBLE_MATH_SYMBOLS = ("=", "√", "∠", "°", "^", "\\angle", "\\sqrt", "\\frac", "\\circ")
NOISE_FILE_EXTENSIONS_RE = re.compile(
    r"(?:^|[\\/])[^\\/\n]+\.(?:ttf|otf|png|jpe?g|gif|svg|json|wav|mp3|mp4|webm|txt|md)$",
    flags=re.IGNORECASE,
)
NOISE_PATH_PREFIX_RE = re.compile(r"^[A-Za-z]:[\\/]|^[./]*assets[\\/]|^[./]*fonts[\\/]", flags=re.IGNORECASE)
REGEX_LITERAL_MARKERS = ("\\d", "\\s", "(?", "[^", ".*")


def build_review_input(sample_dir: Path, *, max_code_chars: int = MAX_CODE_CHARS) -> dict[str, Any]:
    sample_dir = Path(sample_dir)
    code_path = sample_dir / "candidate.py"
    if not code_path.exists():
        raise FileNotFoundError(f"candidate.py not found: {code_path}")

    code_text = code_path.read_text(encoding="utf-8")
    tree = _parse_python(code_text)
    scene_classes = _scene_classes(tree)
    current_sample_evidence = _current_sample_evidence(sample_dir)
    current_sample_contracts = _current_sample_contracts(sample_dir)
    return {
        "schema_version": "logic_engine_mvp.review_input.v1",
        "sample_id": sample_dir.name,
        "question": _read_question(sample_dir),
        "current_sample_evidence": current_sample_evidence,
        "current_sample_contracts": current_sample_contracts,
        "scene_classes": scene_classes,
        "string_literals": _string_literals(tree),
        "visible_math_claims": _visible_math_claims(tree),
        "code_excerpt": _truncate(code_text, max_code_chars),
        "code_excerpt_truncated": len(code_text) > max_code_chars,
        "deterministic_logic_facts": extract_deterministic_logic_facts(
            code_text,
            sample_contracts=current_sample_contracts,
        ),
        "evidence_focused_code_excerpts": _evidence_focused_code_excerpts(code_text, current_sample_evidence),
        "focused_code_excerpts": _focused_code_excerpts(code_text, tree),
        "helper_method_excerpts": _helper_method_excerpts(code_text, tree),
        "input_policy": {
            "historical_reports_included": False,
            "purpose": "current_sample_logic_review_only",
            "truncation_is_not_a_code_issue": True,
        },
    }


def write_review_input(sample_dir: Path, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_review_input(sample_dir)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _parse_python(code_text: str) -> ast.AST:
    try:
        return ast.parse(code_text)
    except SyntaxError as exc:
        raise ValueError(f"candidate.py is not parseable: {exc}") from exc


def _read_question(sample_dir: Path) -> str:
    for name in ("question.txt", "problem_text.txt", "problem.md"):
        path = sample_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return ""


def _current_sample_evidence(sample_dir: Path) -> dict[str, Any]:
    for name in ("case_manifest.json", "sample_meta.json"):
        path = sample_dir / name
        if not path.exists():
            continue
        payload = _read_json_object(path)
        evidence = {
            key: payload[key]
            for key in CURRENT_SAMPLE_EVIDENCE_KEYS
            if key in payload and payload[key] not in ("", None, [], {})
        }
        if evidence:
            return {"source": name, **evidence}
    return {"source": "none"}


def _current_sample_contracts(sample_dir: Path) -> list[dict[str, Any]]:
    for name in ("case_manifest.json", "sample_meta.json"):
        path = sample_dir / name
        if not path.exists():
            continue
        payload = _read_json_object(path)
        contracts = payload.get("contracts")
        if not isinstance(contracts, list):
            continue
        return [
            sanitized
            for item in contracts
            if isinstance(item, dict)
            for sanitized in [_sanitize_contract(item)]
            if sanitized
        ]
    return []


CONTRACT_NOISE_KEYS = {
    "server_refs",
    "code_url",
    "report_url",
    "source_url",
    "source_job",
    "source_stage",
    "source_record_id",
}


def _sanitize_contract(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitized
            for key, item in value.items()
            if str(key) not in CONTRACT_NOISE_KEYS
            for sanitized in [_sanitize_contract(item)]
            if sanitized not in ("", None, [], {})
        }
    if isinstance(value, list):
        return [
            sanitized
            for item in value
            for sanitized in [_sanitize_contract(item)]
            if sanitized not in ("", None, [], {})
        ]
    return value


def _evidence_focused_code_excerpts(code_text: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    terms = _evidence_search_terms(evidence)
    if not terms:
        return []

    lines = code_text.splitlines()
    hits: list[tuple[int, list[str]]] = []
    for line_no, line in enumerate(lines, start=1):
        matched = [term for term in terms if term in line]
        if matched:
            hits.append((line_no, matched))
    if not hits:
        return []

    excerpts: list[dict[str, Any]] = []
    used_ranges: list[tuple[int, int, set[str]]] = []
    for line_no, matched in hits:
        start = max(1, line_no - EVIDENCE_FOCUSED_WINDOW_LINES)
        end = min(len(lines), line_no + EVIDENCE_FOCUSED_WINDOW_LINES)
        merged = False
        for index, (existing_start, existing_end, existing_terms) in enumerate(used_ranges):
            if start <= existing_end + 1 and end >= existing_start - 1:
                used_ranges[index] = (
                    min(existing_start, start),
                    max(existing_end, end),
                    existing_terms | set(matched),
                )
                merged = True
                break
        if not merged:
            used_ranges.append((start, end, set(matched)))

    for start, end, matched_terms in used_ranges[:MAX_EVIDENCE_FOCUSED_EXCERPTS]:
        excerpt_lines = lines[start - 1 : end]
        code = "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(excerpt_lines, start=start))
        excerpts.append(
            {
                "kind": "current_sample_evidence_match",
                "line_start": start,
                "line_end": end,
                "matched_terms": sorted(matched_terms, key=lambda term: (-len(term), term)),
                "code": _truncate_plain(code, MAX_EVIDENCE_FOCUSED_EXCERPT_CHARS),
            }
        )
    return excerpts


def _evidence_search_terms(evidence: dict[str, Any]) -> list[str]:
    texts = [
        str(evidence.get(key) or "")
        for key in ("visible_error_description", "expected_visual_change", "expected_outcome")
    ]
    joined = "\n".join(text for text in texts if text.strip())
    if not joined:
        return []

    terms: list[str] = []
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_']*", joined):
        term = match.group(0)
        if len(term) >= 3 or "_" in term or "'" in term:
            terms.append(term)

    for match in re.finditer(r"-?\d+(?:\.\d+)?(?:\s*(?:cm|m|°|度))?", joined):
        term = match.group(0).strip()
        if len(term) >= 2:
            terms.append(term)

    return _dedupe_terms(terms)


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen = set()
    unique = []
    for term in sorted((item.strip() for item in terms if item.strip()), key=lambda item: (-len(item), item)):
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(term)
        if len(unique) >= 32:
            break
    return unique


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _scene_classes(tree: ast.AST) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_concrete_scene(node):
            scenes.append({"name": node.name, "line": node.lineno})
    return sorted(scenes, key=lambda item: (item["line"], item["name"]))


def _is_concrete_scene(node: ast.ClassDef) -> bool:
    return _inherits_scene(node) and _has_method(node, "construct")


def _inherits_scene(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Scene":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Scene":
            return True
        if isinstance(base, ast.Name) and base.id.endswith("Scene"):
            return True
    return False


def _has_method(node: ast.ClassDef, name: str) -> bool:
    return any(isinstance(item, ast.FunctionDef) and item.name == name for item in node.body)


def _string_literals(tree: ast.AST) -> list[dict[str, Any]]:
    literals: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        key = (node.lineno, node.value)
        if key in seen:
            continue
        seen.add(key)
        literals.append({"line": node.lineno, "value": node.value})
    return sorted(literals, key=lambda item: (item["line"], item["value"]))


def _visible_math_claims(tree: ast.AST) -> list[dict[str, Any]]:
    scene_ranges = _concrete_scene_ranges(tree)
    if not scene_ranges:
        return []

    claims: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        line = int(getattr(node, "lineno", 0) or 0)
        if not any(start <= line <= end for start, end in scene_ranges):
            continue
        value = node.value.strip()
        key = (line, value)
        if key in seen:
            continue
        seen.add(key)
        score = _visible_math_claim_score(value)
        if score <= 0:
            continue
        claims.append(
            {
                "line": line,
                "value": _truncate_plain(value, MAX_VISIBLE_MATH_CLAIM_CHARS),
                "score": score,
                "source": "scene_string_literal",
            }
        )

    ranked = sorted(claims, key=lambda item: (-int(item["score"]), int(item["line"]), str(item["value"])))
    return sorted(ranked[:MAX_VISIBLE_MATH_CLAIMS], key=lambda item: (int(item["line"]), str(item["value"])))


def _concrete_scene_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    ranges = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not _is_concrete_scene(node):
            continue
        start = int(getattr(node, "lineno", 0) or 0)
        end = int(getattr(node, "end_lineno", start) or start)
        if start and end >= start:
            ranges.append((start, end))
    return ranges


def _visible_math_claim_score(value: str) -> int:
    text = value.strip()
    if len(text) < 2 or _is_noise_literal(text):
        return 0

    score = 0
    if _contains_cjk(text):
        score += 4
    score += min(18, sum(3 for keyword in VISIBLE_MATH_KEYWORDS if keyword in text))
    if any(symbol in text for symbol in VISIBLE_MATH_SYMBOLS):
        score += 6
    if any(ch.isdigit() for ch in text):
        score += 3
    if len(text) <= MAX_VISIBLE_MATH_CLAIM_CHARS:
        score += 1
    return score if score >= 6 else 0


def _is_noise_literal(value: str) -> bool:
    text = value.strip()
    if NOISE_PATH_PREFIX_RE.search(text) or NOISE_FILE_EXTENSIONS_RE.search(text):
        return True
    if not _contains_cjk(text) and any(marker in text for marker in REGEX_LITERAL_MARKERS):
        return True
    if re.fullmatch(r"[A-Za-z0-9_.:/\\-]+", text) and not any(ch.isdigit() for ch in text):
        return True
    return False


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in value)


def _focused_code_excerpts(code_text: str, tree: ast.AST) -> list[dict[str, Any]]:
    lines = code_text.splitlines()
    excerpts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not _is_concrete_scene(node):
            continue
        start = max(1, node.lineno - 20)
        end_line = int(getattr(node, "end_lineno", node.lineno + 240) or node.lineno + 240)
        end = min(len(lines), end_line + 20)
        excerpt_lines = lines[start - 1 : end]
        code = "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(excerpt_lines, start=start))
        excerpts.append(
            {
                "kind": "scene_class",
                "class_name": node.name,
                "line_start": start,
                "line_end": end,
                "code": _truncate_plain(code, MAX_FOCUSED_EXCERPT_CHARS),
            }
        )
    return sorted(excerpts, key=lambda item: (item["line_start"], item["class_name"]))


def _helper_method_excerpts(code_text: str, tree: ast.AST) -> list[dict[str, Any]]:
    lines = code_text.splitlines()
    definitions = _method_definitions(tree)
    pending = _construct_self_method_calls(tree)
    seen: set[str] = set()
    excerpts: list[dict[str, Any]] = []

    while pending:
        method_name = pending.pop()
        if method_name in seen or method_name == "construct":
            continue
        seen.add(method_name)
        if not _is_logic_helper_name(method_name):
            continue
        for class_name, node in definitions.get(method_name, []):
            if len(excerpts) >= MAX_HELPER_METHOD_EXCERPTS:
                return sorted(excerpts, key=lambda item: (item["line_start"], item["class_name"], item["method_name"]))
            start = max(1, node.lineno - 3)
            end_line = int(getattr(node, "end_lineno", node.lineno + 80) or node.lineno + 80)
            end = min(len(lines), end_line + 3)
            excerpt_lines = lines[start - 1 : end]
            code = "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(excerpt_lines, start=start))
            excerpts.append(
                {
                    "kind": "helper_method",
                    "class_name": class_name,
                    "method_name": method_name,
                    "line_start": start,
                    "line_end": end,
                    "code": _truncate_plain(code, MAX_FOCUSED_EXCERPT_CHARS),
                }
            )
            pending.update(_self_method_calls(node) - seen)

    return sorted(excerpts, key=lambda item: (item["line_start"], item["class_name"], item["method_name"]))


def _is_logic_helper_name(name: str) -> bool:
    if name in ORCHESTRATION_HELPERS or name.startswith(ORCHESTRATION_PREFIXES):
        return False
    return name.startswith(LOGIC_HELPER_PREFIXES) or any(keyword in name for keyword in LOGIC_HELPER_KEYWORDS)


def _method_definitions(tree: ast.AST) -> dict[str, list[tuple[str, ast.FunctionDef]]]:
    definitions: dict[str, list[tuple[str, ast.FunctionDef]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                definitions.setdefault(item.name, []).append((node.name, item))
    return definitions


def _construct_self_method_calls(tree: ast.AST) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not _is_concrete_scene(node):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "construct":
                calls.update(_self_method_calls(item))
    return calls


def _self_method_calls(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Attribute):
            continue
        value = item.func.value
        if isinstance(value, ast.Name) and value.id == "self":
            calls.add(item.func.attr)
    return calls


def _truncate(text: str, max_chars: int) -> str:
    return _truncate_plain(text, max_chars)


def _truncate_plain(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]
