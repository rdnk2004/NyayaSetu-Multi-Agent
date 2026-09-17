"""
Unit tests for Critic Agent (src/critic_agent.py).

Tests:
1. Normal answer with no issues gets approved=True with the answer unchanged.
2. Already-unverified fallback answer is passed through without an LLM call
   (call_llm_structured is never called).
3. Debate flagged grey-zone but answer states something with unwarranted certainty:
   critic sets approved=False, revises answer, and sets flagged_grey_zone_conflict=True.
4. Malformed LLM response or LLM exception fails safe to approved=True with
   the original answer unchanged.

Run:
  pytest tests/test_critic_agent.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from critic_agent import run_final_critique
from models import (
    CaseBrief,
    CitationVerificationResult,
    CriticResult,
    DebateResult,
)


def test_normal_answer_approved_unchanged():
    """
    (1) A normal answer with no issues gets approved=True with the answer unchanged.
    """
    case_brief = CaseBrief(
        domain="Consumer Protection",
        facts={
            "what_was_bought_or_hired": "Smartphone",
            "what_went_wrong": "Battery defective",
            "amount_paid": "20000 INR",
        },
        ready=True,
    )

    orig_answer = (
        "Under Section 35 of the Consumer Protection Act, 2019, you may file a complaint "
        "before the District Commission regarding the defective smartphone."
    )

    verification_result = CitationVerificationResult(
        verified=True,
        verified_sections=["35"],
        rejected_sections=[],
        final_answer=orig_answer,
    )

    debate_result = DebateResult(
        is_grey_zone=False,
        clearly_supported_side="plaintiff",
        judge_summary="Section 35 clearly provides the consumer with a right to file a complaint.",
    )

    mock_llm_output = json.dumps({
        "approved": True,
        "final_answer": orig_answer,
        "critique_notes": "Answer accurately reflects Section 35 with well-calibrated legal remedies.",
        "flagged_grey_zone_conflict": False,
    })

    with patch("critic_agent.call_llm_structured", return_value=mock_llm_output) as mock_llm:
        result = run_final_critique(case_brief, verification_result, debate_result)

    mock_llm.assert_called_once()
    assert isinstance(result, CriticResult)
    assert result.approved is True
    assert result["approved"] is True
    assert result.final_answer == orig_answer
    assert result["final_answer"] == orig_answer
    assert result.flagged_grey_zone_conflict is False
    assert result["flagged_grey_zone_conflict"] is False
    assert "well-calibrated" in result.critique_notes.lower() or len(result.critique_notes) > 0


def test_unverified_fallback_skips_llm_call():
    """
    (2) An already-unverified fallback answer is passed through without an LLM call
    (mock call_llm_structured and assert it was never called).
    """
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {"what_was_bought_or_hired": "Vehicle"},
        "ready": True,
    }

    fallback_answer = (
        "The legal citations in the generated answer could not be verified against the official "
        "statutory provisions. The situation remains unclear and requires manual legal review."
    )

    verification_result = CitationVerificationResult(
        verified=False,
        verified_sections=[],
        rejected_sections=["999"],
        final_answer=fallback_answer,
    )

    debate_result = DebateResult(
        is_grey_zone=True,
        judge_summary="Ambiguous issue.",
    )

    with patch("critic_agent.call_llm_structured") as mock_llm:
        result = run_final_critique(case_brief, verification_result, debate_result)

    # LLM must NOT be called for already-unverified fallback
    mock_llm.assert_not_called()
    assert isinstance(result, CriticResult)
    assert result.approved is True
    assert result.final_answer == fallback_answer
    assert result.flagged_grey_zone_conflict is False
    assert "Skipped - underlying answer already unverified" in result.critique_notes


def test_debate_grey_zone_conflict_flagged():
    """
    (3) Debate flagged grey-zone but the answer states something with unwarranted certainty.
    Critic should set approved=False (or revise the answer), and flagged_grey_zone_conflict must be True.
    """
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Commercial Espresso Machine",
            "what_went_wrong": "Boiler burst, seller claims third-party parts were used",
            "amount_paid": "180000 INR",
        },
        "ready": True,
    }

    overconfident_answer = (
        "Under Section 2(11), the manufacturer is 100% guaranteed liable for all damages, and you will definitely win "
        "full compensation without any risk of defense exceptions applying."
    )

    verification_result = CitationVerificationResult(
        verified=True,
        verified_sections=["2(11)"],
        rejected_sections=[],
        final_answer=overconfident_answer,
    )

    debate_result = DebateResult(
        is_grey_zone=True,
        clearly_supported_side=None,
        judge_summary=(
            "Genuine statutory conflict: While Section 2(11) defines deficiency broadly, "
            "Section 87 creates an exception for unauthorized third-party modification."
        ),
    )

    softened_answer = (
        "While Section 2(11) establishes provider liability for service deficiency, this dispute "
        "involves a genuine legal grey zone under Section 87 regarding unauthorized modifications. "
        "Liability is contested rather than guaranteed."
    )

    mock_critic_response = json.dumps({
        "approved": False,
        "final_answer": softened_answer,
        "critique_notes": (
            "Flagged grey-zone conflict: Debate identified genuine statutory ambiguity between "
            "Section 2(11) and Section 87 exceptions, but the original answer made unwarranted promises of guaranteed success."
        ),
        "flagged_grey_zone_conflict": True,
    })

    with patch("critic_agent.call_llm_structured", return_value=mock_critic_response) as mock_llm:
        result = run_final_critique(case_brief, verification_result, debate_result)

    mock_llm.assert_called_once()
    assert isinstance(result, CriticResult)
    assert result.approved is False
    assert result["approved"] is False
    assert result.flagged_grey_zone_conflict is True
    assert result["flagged_grey_zone_conflict"] is True
    assert result.final_answer == softened_answer
    assert result.final_answer != overconfident_answer
    assert "grey-zone conflict" in result.critique_notes.lower()


def test_malformed_llm_response_fails_safe():
    """
    (4) A malformed LLM response or unexpected exception fails safe to approved=True
    with the original answer unchanged.
    """
    case_brief = {
        "domain": "Consumer Protection",
        "facts": {"what_was_bought_or_hired": "Air Conditioner"},
        "ready": True,
    }

    orig_answer = "Under Section 35, you may file a complaint with the District Commission."

    verification_result = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "final_answer": orig_answer,
    }

    debate_result = {
        "is_grey_zone": False,
        "judge_summary": "Clear statutory right.",
    }

    malformed_responses = [
        "Not valid json at all",
        "{broken json",
        "",
        json.dumps(["not", "a", "dictionary"]),
    ]

    for bad in malformed_responses:
        with patch("critic_agent.call_llm_structured", return_value=bad):
            result = run_final_critique(case_brief, verification_result, debate_result)

        assert isinstance(result, CriticResult)
        assert result.approved is True
        assert result.final_answer == orig_answer
        assert result.flagged_grey_zone_conflict is False
        assert "unparseable" in result.critique_notes.lower()

    # Also test when call_llm_structured raises an exception (e.g. Gemini timeout or quota)
    with patch("critic_agent.call_llm_structured", side_effect=RuntimeError("API quota exhausted")):
        res_exc = run_final_critique(case_brief, verification_result, debate_result)

    assert isinstance(res_exc, CriticResult)
    assert res_exc.approved is True
    assert res_exc.final_answer == orig_answer
    assert res_exc.flagged_grey_zone_conflict is False
    assert "failed" in res_exc.critique_notes.lower()


def test_grey_zone_conflict_not_set_when_debate_is_none():
    """
    Defensive requirement: flagged_grey_zone_conflict should only ever be checked/set
    when debate_result is not None.
    """
    case_brief = {"domain": "Consumer Protection", "facts": {"item": "TV"}}
    orig_answer = "Under Section 35 you can file a complaint."
    verification_result = {
        "verified": True,
        "verified_sections": ["35"],
        "final_answer": orig_answer,
    }

    # Even if LLM erroneously outputs flagged_grey_zone_conflict: true when debate_result is None
    mock_llm_output = json.dumps({
        "approved": True,
        "final_answer": orig_answer,
        "critique_notes": "All checks passed.",
        "flagged_grey_zone_conflict": True,  # Erroneously true from LLM
    })

    with patch("critic_agent.call_llm_structured", return_value=mock_llm_output):
        result = run_final_critique(case_brief, verification_result, None)

    # Must be forced to False because debate_result is None
    assert result.flagged_grey_zone_conflict is False


if __name__ == "__main__":
    print("\nRunning Critic Agent Unit Tests:")
    test_normal_answer_approved_unchanged()
    test_unverified_fallback_skips_llm_call()
    test_debate_grey_zone_conflict_flagged()
    test_malformed_llm_response_fails_safe()
    test_grey_zone_conflict_not_set_when_debate_is_none()
    print("\nAll Critic Agent unit tests passed successfully!")
