"""
Unit tests for the NyayaSetu Orchestrator (src/orchestrator.py).

Mocks understand_query, IntakeSession, answer_question (QA), and verify_citations to test:
  (1) A message with domain="unclear" stops immediately without creating an intake session.
  (2) A full multi-turn flow: start() returns a question, answer_question() called twice more,
      then final stage is "complete" with the mocked verification result.
  (3) When checklist is already full from the first message, start() skips straight to "complete"
      without any intake_question stage.
  (4) A final_check gap gets surfaced once as its own stage, then proceeds to "complete".

Run:
  python tests/test_orchestrator.py
or:
  pytest tests/test_orchestrator.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from orchestrator import CaseSession


def test_unclear_domain_stops_immediately():
    """
    (1) A message with domain="unclear" stops immediately without creating an intake session.
    """
    session = CaseSession()
    assert session.state == "intake"
    assert session.intake_session is None
    assert session.domain is None
    assert session.final_result is None

    with patch("orchestrator.understand_query") as mock_understand:
        mock_understand.return_value = {"domain": "unclear", "facts": {}}

        result = session.start("Can you write a poem about flowers?")

        assert result["stage"] == "unclear_domain"
        assert "message" in result
        assert len(result["message"]) > 0
        assert session.intake_session is None
        assert session.domain == "unclear"
        assert session.state == "unclear_domain"
        assert session.final_result is None
        mock_understand.assert_called_once_with("Can you write a poem about flowers?")

    print("  Test 1 passed: unclear domain stops immediately without creating an intake session.")


def test_full_multi_turn_flow():
    """
    (2) Full multi-turn flow: start() returns a question, answer_question() called twice more,
        then final stage is "complete" with the mocked verification result.
    """
    session = CaseSession()

    mock_qa_result = {
        "answer": "Under Section 35 of the Consumer Protection Act, 2019, you can file a complaint.",
        "cited_sections": ["35"],
        "status": "answered",
        "retrieved_chunks": [
            {
                "id": "chunk_0035",
                "text": "A complaint in relation to any goods sold... may be filed with a District Commission.",
                "metadata": {"section": "35", "title": "Manner in which complaint shall be made"},
            }
        ],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "details": {"35": {"supported": True, "reason": "Section 35 authorizes complaint filing."}},
        "final_answer": "Under Section 35 of the Consumer Protection Act, 2019, you can file a complaint.",
    }

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
        }

        mock_intake = MockIntakeSession.return_value
        # 1st call (during start()): returns first question
        # 2nd call (during 1st answer_question): returns second question
        # 3rd call (during 2nd answer_question): returns None (complete)
        mock_intake.next_question.side_effect = [
            {"field_key": "what_went_wrong", "question_text": "What went wrong with the laptop?"},
            {"field_key": "amount_paid", "question_text": "How much did you pay for the laptop?"},
            None,
        ]
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": {
                "what_was_bought_or_hired": "Laptop",
                "what_went_wrong": "Screen does not power on",
                "amount_paid": "65000 INR",
            },
            "ready": True,
        }

        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification

        # Step 1: Citizen starts interaction
        res1 = session.start("I bought a laptop and have a defect issue.")
        assert res1["stage"] == "intake_question"
        assert res1["field_key"] == "what_went_wrong"
        assert res1["question_text"] == "What went wrong with the laptop?"
        assert session.state == "intake_question"
        assert session.domain == "Consumer Protection"
        MockIntakeSession.assert_called_once_with(
            domain="Consumer Protection",
            known_facts={"what_was_bought_or_hired": "Laptop"},
        )

        # Step 2: Citizen answers first question
        res2 = session.answer_question("what_went_wrong", "Screen does not power on")
        assert res2["stage"] == "intake_question"
        assert res2["field_key"] == "amount_paid"
        assert res2["question_text"] == "How much did you pay for the laptop?"
        assert session.state == "intake_question"
        mock_intake.record_answer.assert_called_with("what_went_wrong", "Screen does not power on")

        # Step 3: Citizen answers second question -> triggers finish intake
        res3 = session.answer_question("amount_paid", "65000 INR")
        assert res3["stage"] == "complete"
        assert res3["verified"] is True
        assert res3["final_answer"] == mock_verification["final_answer"]
        assert res3["verified_sections"] == ["35"]
        assert res3["rejected_sections"] == []
        assert session.state == "complete"
        assert session.final_result == mock_verification
        mock_intake.record_answer.assert_called_with("amount_paid", "65000 INR")

        mock_qa.assert_called_once_with(mock_intake.to_case_brief.return_value)
        mock_verify.assert_called_once_with(mock_qa_result, mock_qa_result["retrieved_chunks"])

    print("  Test 2 passed: full multi-turn intake flow to complete QA & verification.")


def test_checklist_full_skips_straight_to_complete():
    """
    (3) When checklist is already full from the first message, start() skips straight
        to "complete" without any intake_question stage.
    """
    session = CaseSession()

    complete_facts = {
        "what_was_bought_or_hired": "Washing machine",
        "what_went_wrong": "Cracked drum",
        "when_it_happened": "3 weeks ago",
        "amount_paid": "18000 rupees",
        "seller_or_provider": "Online seller",
    }

    mock_qa_result = {
        "answer": "You can file a complaint with the District Commission.",
        "cited_sections": ["35"],
        "status": "answered",
        "retrieved_chunks": [{"metadata": {"section": "35"}, "text": "..."}],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "You can file a complaint with the District Commission.",
    }

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": complete_facts,
        }

        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = None  # No questions needed!
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": complete_facts,
            "ready": True,
        }
        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification

        result = session.start(
            "I bought a washing machine online 3 weeks ago for 18000 rupees from an online seller and it arrived with a cracked drum."
        )

        # Skips straight to complete stage
        assert result["stage"] == "complete"
        assert result["verified"] is True
        assert result["final_answer"] == mock_verification["final_answer"]
        assert result["verified_sections"] == ["35"]
        assert result["rejected_sections"] == []
        assert session.state == "complete"
        assert session.final_result == mock_verification

        # Verification that QA and citation verification were called
        mock_qa.assert_called_once()
        mock_verify.assert_called_once()

    print("  Test 3 passed: checklist full skips straight to complete stage.")


def test_final_check_gap_surfaced_once():
    """
    (4) A final_check gap gets surfaced once as its own stage.
        Subsequent proceed() or finish transitions to "complete" without re-looping the gap.
    """
    session = CaseSession()

    mock_qa_result = {
        "answer": "Remedy available under Consumer Protection Act.",
        "cited_sections": ["86"],
        "status": "answered",
        "retrieved_chunks": [{"metadata": {"section": "86"}, "text": "..."}],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["86"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Remedy available under Consumer Protection Act.",
    }

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Refrigerator"},
        }

        mock_intake = MockIntakeSession.return_value
        # Single question, then done
        mock_intake.next_question.side_effect = [
            {"field_key": "what_went_wrong", "question_text": "What went wrong?"},
            None,
        ]
        # Flag a gap during final check
        mock_intake.run_final_check.return_value = "Missing invoice number or proof of payment document."
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Refrigerator", "what_went_wrong": "Defective cooling"},
            "ready": True,
        }
        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification

        # Start session
        r1 = session.start("Bought refrigerator")
        assert r1["stage"] == "intake_question"

        # Answer question -> checklist complete -> _finish_intake() surfaces gap ONCE
        r2 = session.answer_question("what_went_wrong", "Defective cooling")
        assert r2["stage"] == "final_check_gap"
        assert r2["gap"] == "Missing invoice number or proof of payment document."
        assert session.state == "final_check_gap"
        # Verify QA has NOT been run yet
        mock_qa.assert_not_called()

        # Caller chooses to proceed anyway
        r3 = session.proceed()
        assert r3["stage"] == "complete"
        assert r3["verified"] is True
        assert r3["final_answer"] == mock_verification["final_answer"]
        assert session.state == "complete"
        # Verify QA and verification were run on proceed
        mock_qa.assert_called_once()
        mock_verify.assert_called_once()
        # Verify run_final_check was only called once
        assert mock_intake.run_final_check.call_count == 1

    print("  Test 4 passed: final check gap surfaced once as its own stage.")


def test_answer_question_without_start_raises():
    """Defensive check: answer_question() before start() raises ValueError."""
    session = CaseSession()
    try:
        session.answer_question("field", "value")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Session has not started intake" in str(e)
    print("  Defensive check passed: answer_question before start raises ValueError.")


if __name__ == "__main__":
    print("\nRunning CaseSession Orchestrator Unit Tests:")
    test_unclear_domain_stops_immediately()
    test_full_multi_turn_flow()
    test_checklist_full_skips_straight_to_complete()
    test_final_check_gap_surfaced_once()
    test_answer_question_without_start_raises()
    print("\nAll CaseSession Orchestrator tests passed successfully!")
