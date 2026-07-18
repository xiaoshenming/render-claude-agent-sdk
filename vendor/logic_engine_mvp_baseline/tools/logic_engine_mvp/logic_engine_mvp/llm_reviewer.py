from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from .llm_client import LlmResponse, chat_completion
from .logic_facts import deterministic_review_issues
from .review_input import build_review_input
from .settings import LlmConfig


ChatFunc = Callable[..., LlmResponse]
REVIEW_PARSE_EXCEPTIONS = (json.JSONDecodeError, ValueError)
MAX_MINIMAL_FOCUSED_EXCERPT_CHARS = 4_000
MAX_REVIEWER_FOCUSED_EXCERPTS = 4
MAX_REVIEWER_FOCUSED_EXCERPT_CHARS = 7_000
MAX_REVIEWER_HELPER_EXCERPTS = 6
MAX_REVIEWER_HELPER_EXCERPT_CHARS = 2_500
MAX_REVIEWER_STRING_LITERALS = 30
MAX_REVIEWER_VISIBLE_MATH_CLAIMS = 36
MAX_PRIMARY_VISIBLE_PROBLEM_CLAIMS = 12
MAX_REVIEWER_LITERAL_CHARS = 220
MAX_REVIEWER_CODE_EXCERPT_CHARS = 6_000

MATH_LITERAL_KEYWORDS = (
    "答案",
    "结论",
    "证明",
    "因为",
    "所以",
    "角",
    "边",
    "面积",
    "长度",
    "半径",
    "直径",
    "坐标",
    "斜率",
    "方程",
    "等于",
    "相似",
    "全等",
    "平行",
    "垂直",
    "中点",
    "对称",
    "折叠",
    "=",
    "\\",
    "^",
    "_",
    "√",
    "∠",
    "°",
)
PROBLEM_CLAIM_KEYWORDS = (
    "题目",
    "例题",
    "已知",
    "求",
    "问",
    "则",
    "答案",
    "结论",
    "证明",
    "____",
    "？",
    "?",
)


REVIEWER_SYSTEM_PROMPT = """You are the Logic Engine reviewer for rendered Manim math videos.

Scope:
- Review only the current sample.
- Do not use historical reports, dataset memories, or external examples as evidence.
- primary_review_packet is the first-pass evidence; check primary_review_packet first before reading long code excerpts.
- current_sample_evidence is allowed because it comes from the current sample directory; use it to focus review, but confirm the defect against candidate.py evidence.
- current_sample_contracts are structured current-sample validation targets; use them to focus review, but do not treat them as a repair by themselves.
- deterministic_logic_facts are computation-only facts extracted from candidate.py; use them before subjective reasoning.
- visible_math_claims are likely rendered or narrated math statements from the selected scene code; compare them with question and current_sample_evidence before returning pass.
- focused_string_literals are visible text/math strings from the selected scene ranges; use them before the larger code excerpts.
- Use evidence_focused_code_excerpts first when present; they are deterministic candidate.py snippets matched from current_sample_evidence terms.
- Do not repair code.
- Do not review layout overlap; overlap has a separate tool.
- Use focused_code_excerpts as the primary code evidence when code_excerpt is truncated.
- Do not report input truncation or missing excerpts as a code defect.
- Report only objective mathematical or logical defects that change the rendered lesson's meaning.
- If question is non-empty and visible_math_claims or focused excerpts solve a different problem, use issue_type problem_mismatch. If the correct fix is not a small exact candidate.py replacement, set repairability to needs_human_review instead of pass.
- Ignore optional visual polish, missing emphasis, pedagogy style, TTS wording, or incomplete-but-not-wrong visual aids.
- Return at most 3 issues. Prefer issues that are directly repairable in candidate.py.
- If your evidence says the math/logic is correct or not an error, do not include that item as an issue.
- Output JSON only.

For every issue, include:
- issue_type
- severity
- confidence
- evidence, 160 chars max
- wrong_text or wrong_claim, 120 chars max
- expected, 120 chars max, or needs_review_reason when not safely verifiable
- exact_code_before when a directly repairable defect maps to a concrete code line; copy the exact candidate.py line without line number when possible
- exact_code_after when the correct replacement is known; provide the exact replacement line when possible
- needs_python_verifier
- repairability

If the code line is too long, put a stable skeleton in wrong_text/expected, e.g. name = self.helper(arg1, wrong_arg, ...)
and still keep the issue objective. Do not invent code identifiers that are not present in candidate.py.
For proof or derivation errors, exact_code_after must remove or correct the false claim; do not merely soften wording while leaving the same false implication/formula in place.
If a problem is subjective, ambiguous, or not verifiable, set repairability to needs_human_review.
"""


def review_sample(
    sample_dir: Path,
    out_path: Path,
    config: LlmConfig,
    *,
    chat: ChatFunc = chat_completion,
) -> Path:
    sample_dir = Path(sample_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    review_input = build_review_input(sample_dir)
    started = time.monotonic()
    deterministic_issues = deterministic_review_issues(review_input)
    if deterministic_issues:
        elapsed_sec = round(time.monotonic() - started, 3)
        normalized = _normalize_review_payload(
            sample_dir.name,
            {
                "issues": deterministic_issues,
                "decision": "needs_human_review",
                "review_mode": "deterministic",
            },
            LlmResponse(
                content="",
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "attempt_count": 0,
                },
                raw={"source": "deterministic_logic_facts"},
            ),
            retry_count=0,
            elapsed_sec=elapsed_sec,
        )
        normalized["review_mode"] = "deterministic"
        out_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path

    response = chat(
        config,
        _build_messages(review_input, compact=False),
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    retry_count = 0
    responses = [response]
    try:
        payload = parse_review_json(response.content)
    except REVIEW_PARSE_EXCEPTIONS:
        retry_count = 1
        response = chat(
            config,
            _build_messages(review_input, compact=True),
            max_tokens=3072,
            response_format={"type": "json_object"},
        )
        responses.append(response)
        try:
            payload = parse_review_json(response.content)
        except REVIEW_PARSE_EXCEPTIONS as exc:
            if _should_use_minimal_fallback(response):
                retry_count = 2
                response = chat(
                    config,
                    _build_minimal_fallback_messages(sample_dir, review_input),
                    max_tokens=768,
                    response_format={"type": "json_object"},
                )
                responses.append(response)
                try:
                    payload = parse_review_json(response.content)
                except REVIEW_PARSE_EXCEPTIONS as fallback_exc:
                    _write_review_error(
                        out_path.with_name("llm_review_error.json"),
                        fallback_exc,
                        _with_merged_usage(response, responses),
                    )
                    payload = _safe_human_review_payload(sample_dir.name, fallback_exc)
            else:
                _write_review_error(out_path.with_name("llm_review_error.json"), exc, _with_merged_usage(response, responses))
                payload = _safe_human_review_payload(sample_dir.name, exc)
    except Exception as exc:
        _write_review_error(out_path.with_name("llm_review_error.json"), exc, _with_merged_usage(response, responses))
        raise
    response = _with_merged_usage(response, responses)
    elapsed_sec = round(time.monotonic() - started, 3)
    normalized = _normalize_review_payload(
        sample_dir.name,
        payload,
        response,
        retry_count=retry_count,
        elapsed_sec=elapsed_sec,
    )
    out_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _safe_human_review_payload(sample_id: str, exc: Exception) -> dict[str, Any]:
    return {
        "issues": [
            {
                "issue_type": "reviewer_output_invalid",
                "severity": "blocking",
                "confidence": 0.0,
                "evidence": "Reviewer returned invalid or truncated JSON after retry attempts.",
                "wrong_claim": "The current sample logic review could not be completed reliably.",
                "needs_review_reason": f"Reviewer returned invalid JSON; automatic repair disabled: {type(exc).__name__}.",
                "needs_python_verifier": False,
                "repairability": "needs_human_review",
                "sample_id": sample_id,
            }
        ],
        "decision": "needs_human_review",
        "safe_fallback_reason": "reviewer_output_invalid",
    }


def _build_messages(review_input: dict[str, Any], *, compact: bool) -> list[dict[str, str]]:
    llm_input = compact_review_input_for_llm(review_input, aggressive=compact)
    if compact:
        instruction = (
            "Retry because the previous response was invalid JSON. "
            "Return compact JSON only. Return {\"issues\":[]} unless there is one objective, "
            "mathematically wrong, directly repairable defect. At most 1 issue."
        )
    else:
        instruction = "Review this current Manim logic sample and return strict JSON."
    return [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{instruction}\n\n{json.dumps(llm_input, ensure_ascii=False)}",
        },
    ]


def compact_review_input_for_llm(
    review_input: dict[str, Any],
    *,
    aggressive: bool = False,
    max_string_literals: int | None = None,
) -> dict[str, Any]:
    """Build the smaller payload sent to the reviewer while keeping full artifacts on disk."""

    literal_limit = max_string_literals or (12 if aggressive else MAX_REVIEWER_STRING_LITERALS)
    focused_limit = 1 if aggressive else MAX_REVIEWER_FOCUSED_EXCERPTS
    helper_limit = 1 if aggressive else MAX_REVIEWER_HELPER_EXCERPTS
    focused_chars = 3_000 if aggressive else MAX_REVIEWER_FOCUSED_EXCERPT_CHARS
    helper_chars = 1_200 if aggressive else MAX_REVIEWER_HELPER_EXCERPT_CHARS

    selected_focused_excerpts = _compact_excerpts(
        _scene_filtered_excerpts(
            review_input.get("focused_code_excerpts"),
            _evidence_scene_name(review_input),
        ),
        max_count=focused_limit,
        max_chars=focused_chars,
    )
    compact: dict[str, Any] = {
        "schema_version": "logic_engine_mvp.review_input.compact.v1",
        "source_schema_version": review_input.get("schema_version"),
        "sample_id": review_input.get("sample_id"),
        "primary_review_packet": _primary_review_packet(review_input),
        "question": review_input.get("question") or "",
        "current_sample_evidence": review_input.get("current_sample_evidence") or {},
        "current_sample_contracts": review_input.get("current_sample_contracts") or [],
        "scene_classes": review_input.get("scene_classes") or [],
        "string_literals": _select_string_literals(review_input.get("string_literals"), literal_limit),
        "visible_math_claims": _select_visible_math_claims(
            review_input.get("visible_math_claims"),
            max_count=18 if aggressive else MAX_REVIEWER_VISIBLE_MATH_CLAIMS,
        ),
        "focused_string_literals": _selected_range_string_literals(
            review_input.get("string_literals"),
            selected_focused_excerpts,
            max_count=literal_limit,
        ),
        "deterministic_logic_facts": review_input.get("deterministic_logic_facts") or [],
        "evidence_focused_code_excerpts": _compact_excerpts(
            review_input.get("evidence_focused_code_excerpts"),
            max_count=focused_limit,
            max_chars=focused_chars,
        ),
        "focused_code_excerpts": selected_focused_excerpts,
        "helper_method_excerpts": _compact_excerpts(
            review_input.get("helper_method_excerpts"),
            max_count=helper_limit,
            max_chars=helper_chars,
        ),
        "code_excerpt_truncated": bool(review_input.get("code_excerpt_truncated")),
        "input_policy": {
            **(review_input.get("input_policy") if isinstance(review_input.get("input_policy"), dict) else {}),
            "full_review_input_artifact_retained": True,
            "llm_payload_compacted": True,
        },
    }
    if not compact["focused_code_excerpts"] and review_input.get("code_excerpt"):
        compact["code_excerpt"] = _truncate_middle(
            str(review_input.get("code_excerpt") or ""),
            MAX_REVIEWER_CODE_EXCERPT_CHARS,
        )
    return compact


def _evidence_scene_name(review_input: dict[str, Any]) -> str:
    evidence = review_input.get("current_sample_evidence")
    if not isinstance(evidence, dict):
        return ""
    return str(evidence.get("scene_name") or "").strip()


def _scene_filtered_excerpts(excerpts: Any, scene_name: str) -> list[dict[str, Any]]:
    items = [item for item in excerpts or [] if isinstance(item, dict)]
    if not scene_name:
        return items
    matched = [item for item in items if _scene_names_match(scene_name, str(item.get("class_name") or ""))]
    return matched or items


def _scene_names_match(evidence_scene: str, class_name: str) -> bool:
    if not evidence_scene or not class_name:
        return False
    evidence_key = evidence_scene.lower()
    class_key = class_name.lower()
    return evidence_key in class_key or class_key in evidence_key


def _compact_excerpts(excerpts: Any, *, max_count: int, max_chars: int) -> list[dict[str, Any]]:
    compact = []
    for item in excerpts or []:
        if not isinstance(item, dict) or len(compact) >= max_count:
            continue
        next_item = {key: value for key, value in item.items() if key != "code"}
        next_item["code"] = _truncate_middle(str(item.get("code") or ""), max_chars)
        compact.append(next_item)
    return compact


def _primary_review_packet(review_input: dict[str, Any]) -> dict[str, Any]:
    question = str(review_input.get("question") or "").strip()
    visible_problem_claims = _select_visible_problem_claims(
        review_input.get("visible_math_claims"),
        max_count=MAX_PRIMARY_VISIBLE_PROBLEM_CLAIMS,
    )
    return {
        "question": question,
        "problem_alignment_check_required": bool(question and visible_problem_claims),
        "visible_problem_claims": visible_problem_claims,
        "current_sample_evidence": review_input.get("current_sample_evidence") or {},
        "current_sample_contracts": review_input.get("current_sample_contracts") or [],
    }


def _select_visible_problem_claims(claims: Any, *, max_count: int) -> list[dict[str, Any]]:
    items = [item for item in claims or [] if isinstance(item, dict)]
    problem_like = [item for item in items if _looks_like_problem_claim(str(item.get("value") or ""))]
    selected = problem_like or items
    ranked = sorted(
        enumerate(selected),
        key=lambda pair: (-_int(pair[1].get("score")), _literal_line(pair[1]), pair[0]),
    )
    return [
        {
            **{key: value for key, value in item.items() if key != "value"},
            "value": _truncate_middle(str(item.get("value") or ""), MAX_REVIEWER_LITERAL_CHARS),
        }
        for _, item in sorted(ranked[:max_count], key=lambda pair: _literal_line(pair[1]))
    ]


def _looks_like_problem_claim(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    return any(keyword in text for keyword in PROBLEM_CLAIM_KEYWORDS)


def _select_string_literals(literals: Any, max_count: int) -> list[dict[str, Any]]:
    items = [item for item in literals or [] if isinstance(item, dict)]
    ranked = sorted(enumerate(items), key=lambda pair: (-_literal_score(pair[1]), _literal_line(pair[1]), pair[0]))
    selected = [item for _, item in ranked[:max_count]]
    return [
        {
            **{key: value for key, value in item.items() if key != "value"},
            "value": _truncate_middle(str(item.get("value") or ""), MAX_REVIEWER_LITERAL_CHARS),
        }
        for item in sorted(selected, key=_literal_line)
    ]


def _select_visible_math_claims(claims: Any, *, max_count: int) -> list[dict[str, Any]]:
    items = [item for item in claims or [] if isinstance(item, dict)]
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (-_int(pair[1].get("score")), _literal_line(pair[1]), pair[0]),
    )
    selected = [item for _, item in ranked[:max_count]]
    return [
        {
            **{key: value for key, value in item.items() if key != "value"},
            "value": _truncate_middle(str(item.get("value") or ""), MAX_REVIEWER_LITERAL_CHARS),
        }
        for item in sorted(selected, key=_literal_line)
    ]


def _selected_range_string_literals(
    literals: Any,
    focused_excerpts: list[dict[str, Any]],
    *,
    max_count: int,
) -> list[dict[str, Any]]:
    ranges = []
    for excerpt in focused_excerpts:
        start = _int_or_none(excerpt.get("line_start"))
        end = _int_or_none(excerpt.get("line_end"))
        if start is not None and end is not None:
            ranges.append((start, end))
    if not ranges:
        return []
    in_range = []
    for item in literals or []:
        if not isinstance(item, dict):
            continue
        line = _int_or_none(item.get("line"))
        if line is None:
            continue
        if any(start <= line <= end for start, end in ranges):
            in_range.append(item)
    return _select_string_literals(in_range, max_count)


def _literal_score(item: dict[str, Any]) -> int:
    value = str(item.get("value") or "")
    score = 0
    if any(ch.isdigit() for ch in value):
        score += 4
    if any(keyword in value for keyword in MATH_LITERAL_KEYWORDS):
        score += 5
    if "MathTex" in value or "Tex" in value:
        score += 2
    if len(value) <= MAX_REVIEWER_LITERAL_CHARS:
        score += 1
    return score


def _literal_line(item: dict[str, Any]) -> int:
    try:
        return int(item.get("line") or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_minimal_fallback_messages(sample_dir: Path, review_input: dict[str, Any]) -> list[dict[str, str]]:
    minimal_input = {
        "schema_version": "logic_engine_mvp.minimal_review_input.v1",
        "sample_id": sample_dir.name,
        "case_manifest": _safe_read_json(sample_dir / "case_manifest.json"),
        "sample_meta": _safe_read_json(sample_dir / "sample_meta.json"),
        "current_sample_evidence": review_input.get("current_sample_evidence") or {},
        "visible_math_claims": _select_visible_math_claims(
            review_input.get("visible_math_claims"),
            max_count=12,
        ),
        "evidence_focused_code_excerpts": _compact_excerpts(
            review_input.get("evidence_focused_code_excerpts"),
            max_count=1,
            max_chars=3_000,
        ),
        "focused_code_excerpts": _minimal_focused_code_excerpts(review_input),
        "candidate_excerpt": _candidate_excerpt(sample_dir / "candidate.py"),
    }
    instruction = (
        "The previous reviewer response used all output tokens for reasoning and returned no JSON. "
        "Use this minimal JSON fallback input. Return JSON only. "
        "Return {\"issues\":[]} unless the excerpt contains one objective rendered-math logic error. "
        "At most 1 issue. Do not repair code."
    )
    return [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {"role": "user", "content": f"{instruction}\n\n{json.dumps(minimal_input, ensure_ascii=False)}"},
    ]


def _candidate_excerpt(candidate_path: Path, *, max_lines: int = 80, max_chars: int = 4000) -> dict[str, Any]:
    text = candidate_path.read_text(encoding="utf-8", errors="replace") if candidate_path.exists() else ""
    lines = text.splitlines()
    excerpt_lines = lines[:max_lines]
    excerpt = "\n".join(excerpt_lines)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip()
    return {
        "path": "candidate.py",
        "line_start": 1,
        "line_end": len(excerpt_lines),
        "truncated": len(lines) > len(excerpt_lines) or len("\n".join(excerpt_lines)) > len(excerpt),
        "text": excerpt,
    }


def _minimal_focused_code_excerpts(review_input: dict[str, Any]) -> list[dict[str, Any]]:
    excerpts = review_input.get("focused_code_excerpts") or []
    if not isinstance(excerpts, list):
        return []
    compact = []
    for item in excerpts[:1]:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "kind": item.get("kind"),
                "class_name": item.get("class_name"),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "code": _truncate_middle(str(item.get("code") or ""), MAX_MINIMAL_FOCUSED_EXCERPT_CHARS),
            }
        )
    return compact


def _truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    return text[:head_chars].rstrip() + "\n# ... middle truncated by logic_engine_mvp ...\n" + text[-tail_chars:].lstrip()


def _safe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _should_use_minimal_fallback(response: LlmResponse) -> bool:
    if response.content.strip():
        return False
    completion_tokens = _int(response.usage.get("completion_tokens"))
    reasoning_tokens = _int(
        (response.usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if isinstance(response.usage.get("completion_tokens_details"), dict)
        else 0
    )
    return completion_tokens == 0 or reasoning_tokens >= completion_tokens


def _merge_response_usages(responses: list[LlmResponse]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for response in responses:
        _merge_usage_into(merged, response.usage)
    merged["attempt_count"] = len(responses)
    return merged


def _with_merged_usage(response: LlmResponse, responses: list[LlmResponse]) -> LlmResponse:
    return LlmResponse(content=response.content, usage=_merge_response_usages(responses), raw=response.raw)


def _merge_usage_into(target: dict[str, Any], usage: dict[str, Any]) -> None:
    for key, value in usage.items():
        if isinstance(value, (int, float)):
            target[key] = target.get(key, 0) + value
        elif isinstance(value, dict):
            nested = target.setdefault(key, {})
            if isinstance(nested, dict):
                _merge_usage_into(nested, value)
        elif key not in target:
            target[key] = value


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_review_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        recovered = _recover_truncated_issue_payload(cleaned)
        if recovered is None:
            raise
        return recovered
    if isinstance(data, list):
        data = {"issues": data}
    if not isinstance(data, dict):
        raise ValueError("review payload must be a JSON object")
    if "issues" not in data and _looks_like_issue(data):
        data = {"issues": [data]}
    if "issues" not in data or not isinstance(data["issues"], list):
        raise ValueError("review payload must contain an issues array")
    return data


_TRUNCATED_STRING_FIELD_RE = re.compile(
    r'"(?P<key>issue_type|type|severity|confidence|evidence|reason|statement|wrong_text|wrong_claim|observed|actual|expected|expected_text|correct|target|needs_review_reason|repairability)"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"',
    flags=re.DOTALL,
)


def _recover_truncated_issue_payload(cleaned: str) -> dict[str, Any] | None:
    if '"issues"' not in cleaned and not _looks_like_json_issue_start(cleaned):
        return None
    issue: dict[str, Any] = {}
    for match in _TRUNCATED_STRING_FIELD_RE.finditer(cleaned):
        key = match.group("key")
        if key in issue:
            continue
        issue[key] = _decode_json_string_fragment(match.group("value"))
    if not _is_actionable_issue(issue):
        return None
    return {"issues": [issue], "recovered_from_truncated_json": True}


def _looks_like_json_issue_start(cleaned: str) -> bool:
    return cleaned.lstrip().startswith("{") and '"issue_type"' in cleaned


def _decode_json_string_fragment(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def _normalize_review_payload(
    sample_id: str,
    payload: dict[str, Any],
    response: LlmResponse,
    *,
    retry_count: int = 0,
    elapsed_sec: float | None = None,
) -> dict[str, Any]:
    raw_issues = payload.get("issues") or []
    issues: list[dict[str, Any]] = []
    discarded_issues: list[dict[str, Any]] = []
    for raw_issue in raw_issues:
        if isinstance(raw_issue, dict) and _is_actionable_issue(raw_issue):
            issues.append(raw_issue)
            continue
        discarded_issues.append(_discarded_issue_summary(raw_issue))
    open_repair_issues = [issue for issue in discarded_issues if issue.get("open_repair_candidate")]
    decision = _normalized_decision(payload, issues, open_repair_issues)
    return {
        "schema_version": "logic_engine_mvp.llm_review.v1",
        "sample_id": sample_id,
        "issues": issues,
        "decision": decision,
        "elapsed_sec": elapsed_sec,
        "usage": response.usage,
        "retry_count": retry_count,
        "discarded_issue_count": len(discarded_issues),
        "open_repair_issue_count": len(open_repair_issues),
        "discarded_issues": discarded_issues,
        "reviewer_raw_keys": sorted(str(key) for key in payload.keys()),
    }


def _normalized_decision(
    payload: dict[str, Any],
    issues: list[dict[str, Any]],
    open_repair_issues: list[dict[str, Any]],
) -> str:
    if issues:
        return str(payload.get("decision") or _decision_from_issues(issues))
    if open_repair_issues:
        return "open_repair_candidate"
    return "pass"


def _discarded_issue_summary(raw_issue: Any) -> dict[str, Any]:
    if not isinstance(raw_issue, dict):
        return {
            "discarded_reason": "non_object_issue",
            "open_repair_candidate": False,
            "raw_type": type(raw_issue).__name__,
        }
    evidence = _first_text(raw_issue, "evidence", "reason", "statement")
    issue_type = _first_text(raw_issue, "issue_type", "type")
    wrong = _first_text(raw_issue, "wrong_text", "wrong_claim", "observed", "actual")
    expected = _first_text(raw_issue, "expected", "expected_text", "correct", "target")
    needs_review_reason = _first_text(raw_issue, "needs_review_reason")
    exact_before = _first_text(raw_issue, "exact_code_before")
    exact_after = _first_text(raw_issue, "exact_code_after")
    no_error = _is_no_error_repairability(_first_text(raw_issue, "repairability")) or _is_no_error_evidence(
        evidence.lower()
    )
    same_before_after = bool(exact_before and exact_after and exact_before == exact_after)
    missing_fields = _missing_actionable_fields(issue_type, evidence, wrong, expected, needs_review_reason)
    open_repair_candidate = (
        not no_error
        and not same_before_after
        and bool(issue_type or evidence or wrong)
        and bool(evidence or wrong)
    )
    reason = "missing_required_fields"
    if no_error:
        reason = "no_error"
    elif same_before_after:
        reason = "same_before_after"
    return {
        "issue_type": _clip_text(issue_type),
        "evidence": _clip_text(evidence),
        "wrong_claim": _clip_text(wrong),
        "expected_behavior": _clip_text(expected),
        "needs_review_reason": _clip_text(needs_review_reason),
        "repairability": _clip_text(_first_text(raw_issue, "repairability")),
        "missing_fields": missing_fields,
        "discarded_reason": reason,
        "open_repair_candidate": open_repair_candidate,
    }


def _missing_actionable_fields(
    issue_type: str,
    evidence: str,
    wrong: str,
    expected: str,
    needs_review_reason: str,
) -> list[str]:
    missing = []
    if not issue_type:
        missing.append("issue_type")
    if not evidence:
        missing.append("evidence")
    if not wrong:
        missing.append("wrong_claim")
    if not expected and not needs_review_reason:
        missing.append("expected_or_needs_review_reason")
    return missing


def _clip_text(value: str, limit: int = 800) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _is_actionable_issue(issue: dict[str, Any]) -> bool:
    issue_type = _first_text(issue, "issue_type", "type")
    evidence = _first_text(issue, "evidence", "reason", "statement").lower()
    if not issue_type or not evidence:
        return False
    if _is_no_error_repairability(_first_text(issue, "repairability")):
        return False
    if _is_no_error_evidence(evidence):
        return False
    exact_before = _first_text(issue, "exact_code_before")
    exact_after = _first_text(issue, "exact_code_after")
    if exact_before and exact_after and exact_before == exact_after:
        return False
    wrong = _first_text(issue, "wrong_text", "wrong_claim", "observed", "actual")
    expected = _first_text(issue, "expected", "expected_text", "correct", "target")
    if wrong and (expected or _first_text(issue, "needs_review_reason")):
        return True
    return False


def _looks_like_issue(payload: dict[str, Any]) -> bool:
    return bool(_first_text(payload, "issue_type", "type") and _first_text(payload, "evidence", "reason", "statement"))


def _is_no_error_evidence(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "no math error",
            "no calculation error",
            "no computation error",
            "no logical error",
            "no logic error",
            "not a math error",
            "not a calculation error",
            "not an error",
            "no error found",
            "math logic is correct",
            "logic is correct",
            "the math is correct",
        )
    )


def _is_no_error_repairability(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in {
        "not_an_error",
        "no_error",
        "not_error",
        "correct",
        "not_applicable",
    }


def _first_text(issue: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = issue.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _write_review_error(path: Path, exc: Exception, response: LlmResponse) -> None:
    payload = {
        "schema_version": "logic_engine_mvp.llm_review_error.v1",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "usage": response.usage,
        "raw_content_preview": response.content[:4000],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _decision_from_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "pass"
    if any(str(item.get("repairability")) == "candidate" for item in issues):
        return "repair"
    return "needs_human_review"
