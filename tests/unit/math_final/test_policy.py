from manim_quality.math_final.input_checks import InputEvidence
from manim_quality.math_final.policy import FinalVerdict, decide_final_verdict


def review(classification):
    domain = {
        "core_math": "proof",
        "source_mismatch": "identity",
        "input_invalid": "input",
    }.get(classification, "diagram")
    return {
        "classification": classification,
        "issues": [
            {
                "domain": domain,
                "impact": "core" if domain != "diagram" else "local",
                "affects_final_answer": classification == "core_math",
            }
        ],
    }


def arbitration(classification):
    return {"classification": classification, "confirmed_claim_indexes": [0]}


def test_pass_requires_two_clean_reviews():
    decision = decide_final_verdict([review("pass"), review("pass")])
    assert decision.verdict is FinalVerdict.PASS
    assert decision.needs_arbitration is False


def test_single_core_finding_is_minor_pending_arbitration():
    decision = decide_final_verdict([review("core_math"), review("pass")])
    assert decision.verdict is FinalVerdict.MINOR_ISSUE
    assert decision.needs_arbitration is True


def test_math_error_requires_triple_core_consensus():
    decision = decide_final_verdict(
        [review("core_math"), review("core_math")],
        arbitration=arbitration("core_math"),
    )
    assert decision.verdict is FinalVerdict.MATH_ERROR
    assert decision.failure_code == "CORE_MATH_TRIPLE_CONSENSUS"


def test_diagram_risk_cannot_be_promoted_to_math_error():
    decision = decide_final_verdict(
        [review("diagram_fidelity"), review("diagram_fidelity")],
        arbitration=arbitration("diagram_fidelity"),
    )
    assert decision.verdict is FinalVerdict.MINOR_ISSUE


def test_invalid_input_is_not_ai_math_error():
    decision = decide_final_verdict(
        [review("input_invalid"), review("input_invalid")],
        arbitration=arbitration("input_invalid"),
    )
    assert decision.verdict is FinalVerdict.MINOR_ISSUE
    assert decision.failure_code == "INPUT_INVALID_NOT_AI_MATH_ERROR"


def test_deterministic_identity_mismatch_wins():
    evidence = InputEvidence("SOURCE_SHA_MISMATCH", "source_mismatch", "bad")
    decision = decide_final_verdict(
        [review("pass"), review("pass")],
        input_evidence=[evidence],
    )
    assert decision.verdict is FinalVerdict.SOURCE_MISMATCH


def test_core_classification_without_core_issue_is_downgraded():
    malformed = {"classification": "core_math", "issues": []}
    decision = decide_final_verdict(
        [malformed, malformed],
        arbitration=arbitration("core_math"),
    )
    assert decision.verdict is FinalVerdict.MINOR_ISSUE
