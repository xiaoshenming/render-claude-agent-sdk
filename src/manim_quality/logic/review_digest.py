"""Versioned, diagnosis-free math digest for bounded Logic Review."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import MappingProxyType

from manim_quality.contracts._json_values import freeze_json_object, thaw_json_object
from manim_quality.revisions.fingerprint import code_hash

from .evidence import LogicEvidence

REVIEW_DIGEST_SCHEMA_VERSION = "manim-quality.logic-review-digest.v2"
_MAX_VECTORS = 256
_MAX_CONSTRUCTIONS = 512
_MAX_CLAIMS = 256
_MAX_EXPRESSION_CHARS = 240
_CONSTRUCTORS = frozenset(
    {
        "Angle",
        "Arc",
        "Arrow",
        "Circle",
        "DashedLine",
        "Dot",
        "Line",
        "MathTex",
        "Polygon",
        "RightAngle",
        "Tex",
        "Text",
        "make_angle_with_label",
        "make_equal_angle_label",
        "make_equal_side_marks",
        "make_text",
    }
)


@dataclass(frozen=True, slots=True)
class LogicReviewDigest:
    _payload: MappingProxyType

    def to_prompt_dict(self) -> dict[str, object]:
        return thaw_json_object(self._payload)


def build_review_digest(
    evidence: LogicEvidence, candidate_code: str
) -> LogicReviewDigest:
    if not isinstance(evidence, LogicEvidence):
        raise TypeError("evidence must be LogicEvidence")
    if type(candidate_code) is not str:
        raise TypeError("candidate_code must be a string")
    if code_hash(candidate_code) != evidence.code_hash:
        raise ValueError("candidate code does not match LogicEvidence")
    try:
        tree = ast.parse(candidate_code)
    except SyntaxError as error:
        raise ValueError("candidate code must be valid Python") from error
    engine = evidence.engine_evidence
    vectors = _numeric_vectors(tree)
    constructions = _constructions(tree)
    claims = list(engine["visible_math_claims"])
    payload = {
        "schema_version": REVIEW_DIGEST_SCHEMA_VERSION,
        "problem": evidence.problem.to_prompt_dict(),
        "planning": evidence.planning.to_prompt_dict(),
        "expected_answer": (
            evidence.expected_answer.to_prompt_dict()
            if evidence.expected_answer is not None
            else None
        ),
        "scene_index": [
            {
                "scene_id": scene.scene_id,
                "line_start": scene.line_start,
                "line_end": scene.line_end,
            }
            for scene in evidence.scenes
        ],
        "visible_math_claims": claims[:_MAX_CLAIMS],
        "deterministic_logic_facts": thaw_json_object(
            engine["deterministic_logic_facts"]
        ),
        "numeric_vectors": vectors[:_MAX_VECTORS],
        "constructions": constructions[:_MAX_CONSTRUCTIONS],
        "truncation": {
            "visible_math_claims": max(0, len(claims) - _MAX_CLAIMS),
            "numeric_vectors": max(0, len(vectors) - _MAX_VECTORS),
            "constructions": max(0, len(constructions) - _MAX_CONSTRUCTIONS),
        },
        "input_policy": {
            "external_diagnosis_included": False,
            "repair_hints_included": False,
            "full_source_embedded": False,
            "candidate_readable_on_demand": True,
        },
    }
    return LogicReviewDigest(freeze_json_object(payload, "review_digest"))


def _numeric_vectors(tree: ast.AST) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        name = _assigned_name(node)
        if name is None or not isinstance(value, ast.Call) or not value.args:
            continue
        if _call_name(value.func) not in {"array", "np.array"}:
            continue
        vector = _literal_vector(value.args[0])
        if vector is not None:
            facts.append({"name": name, "line": node.lineno, "value": vector})
    return sorted(facts, key=lambda item: (item["line"], item["name"]))


def _constructions(tree: ast.AST) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        constructor = _call_name(node.func).removeprefix("self.")
        if constructor not in _CONSTRUCTORS:
            continue
        assigned = _parent_assignment_name(tree, node)
        args = [_expression(value) for value in node.args]
        keywords = {
            item.arg: _expression(item.value)
            for item in node.keywords
            if item.arg is not None
        }
        identity = (node.lineno, constructor, tuple(args), tuple(keywords.items()))
        if identity in seen:
            continue
        seen.add(identity)
        facts.append(
            {
                "name": assigned,
                "constructor": constructor,
                "line": node.lineno,
                "arguments": args,
                "keywords": keywords,
            }
        )
    return sorted(facts, key=lambda item: (item["line"], item["constructor"]))


def _parent_assignment_name(tree: ast.AST, target: ast.Call) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is target:
            return _assigned_name(node)
    return None


def _assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _literal_vector(node: ast.AST) -> list[int | float] | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, (list, tuple)) or not value:
        return None
    if any(type(item) not in {int, float} for item in value):
        return None
    return list(value)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _expression(node: ast.AST) -> str:
    value = ast.unparse(node)
    if len(value) <= _MAX_EXPRESSION_CHARS:
        return value
    return value[: _MAX_EXPRESSION_CHARS - 3] + "..."
