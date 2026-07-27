from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .input_checks import InputEvidence


class FinalVerdict(StrEnum):
    PASS = "PASS"
    MINOR_ISSUE = "MINOR_ISSUE"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    MATH_ERROR = "MATH_ERROR"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    verdict: FinalVerdict
    failure_code: str
    explanation: str
    needs_arbitration: bool


def decide_final_verdict(
    reviews: Sequence[Mapping[str, object]],
    *,
    input_evidence: Sequence[InputEvidence] = (),
    arbitration: Mapping[str, object] | None = None,
) -> PolicyDecision:
    if any(item.status == "source_mismatch" for item in input_evidence):
        return _decision(
            FinalVerdict.SOURCE_MISMATCH,
            "DETERMINISTIC_SOURCE_MISMATCH",
            "deterministic source identity evidence failed",
        )
    classes = tuple(_classification(item) for item in reviews)
    if len(classes) < 2:
        return _decision(
            FinalVerdict.MINOR_ISSUE,
            "REVIEW_INCOMPLETE",
            "two independent reviewer results are required",
        )
    risky = [name for name in classes if name != "pass"]
    if not risky:
        return _decision(
            FinalVerdict.PASS,
            "NO_SUPPORTED_CORE_DEFECT",
            "both reviewers passed the core mathematics",
        )
    if arbitration is None:
        return _decision(
            FinalVerdict.MINOR_ISSUE,
            "ARBITRATION_REQUIRED",
            "non-pass evidence requires precision arbitration",
            needs_arbitration=True,
        )
    arb = _arbitration_classification(arbitration)
    if (
        classes.count("source_mismatch") == 2
        and arb == "source_mismatch"
    ):
        return _decision(
            FinalVerdict.SOURCE_MISMATCH,
            "SOURCE_IDENTITY_CONSENSUS",
            "two reviewers and the arbiter confirmed source mismatch",
        )
    if classes.count("core_math") == 2 and arb == "core_math":
        return _decision(
            FinalVerdict.MATH_ERROR,
            "CORE_MATH_TRIPLE_CONSENSUS",
            "two reviewers and the arbiter confirmed a core math defect",
        )
    if classes.count("input_invalid") == 2 and arb == "input_invalid":
        return _decision(
            FinalVerdict.MINOR_ISSUE,
            "INPUT_INVALID_NOT_AI_MATH_ERROR",
            "the input is invalid; do not attribute it as an AI math error",
        )
    return _decision(
        FinalVerdict.MINOR_ISSUE,
        "NON_CORE_OR_DISPUTED_RISK",
        "risk is local, diagram-only, input-side, or disputed",
    )


def _decision(
    verdict: FinalVerdict,
    failure_code: str,
    explanation: str,
    *,
    needs_arbitration: bool = False,
) -> PolicyDecision:
    return PolicyDecision(verdict, failure_code, explanation, needs_arbitration)


def _classification(value: Mapping[str, object]) -> str:
    classification = value.get("classification")
    if not isinstance(classification, str):
        return "unknown"
    raw_issues = value.get("issues", ())
    issues = raw_issues if isinstance(raw_issues, Sequence) else ()
    if classification == "core_math" and not any(
        isinstance(item, Mapping)
        and item.get("domain") in {"answer", "proof"}
        and item.get("impact") == "core"
        and item.get("affects_final_answer") is True
        for item in issues
    ):
        return "minor"
    if classification == "source_mismatch" and not any(
        isinstance(item, Mapping)
        and item.get("domain") == "identity"
        and item.get("impact") == "core"
        for item in issues
    ):
        return "minor"
    if classification == "input_invalid" and not any(
        isinstance(item, Mapping)
        and item.get("domain") == "input"
        and item.get("impact") == "core"
        for item in issues
    ):
        return "minor"
    return classification


def _arbitration_classification(value: Mapping[str, object]) -> str:
    classification = value.get("classification")
    indexes = value.get("confirmed_claim_indexes")
    if classification in {"core_math", "source_mismatch", "input_invalid"}:
        if not isinstance(indexes, Sequence) or not indexes:
            return "minor"
    return classification if isinstance(classification, str) else "unknown"
