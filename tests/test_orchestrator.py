"""
Unit tests for the NyayaSetu Orchestrator (src/orchestrator.py).

Mocks understand_query, IntakeSession, answer_question (QA), verify_citations, retrieve, and run_debate:
  (1) A message with domain="unclear" stops immediately without creating an intake session.
  (2) A full multi-turn flow: start() returns a question, answer_question() called twice more,
      then final stage is "complete" with verification and populated debate (using wider top_k chunks).
  (3) When checklist is already full from the first message, start() skips straight to "complete"
      without any intake_question stage.
  (4) A final_check gap gets surfaced once as its own stage, then proceeds to "complete".
  (5) When run_debate raises an exception (e.g. quota limit), the orchestrator catches it,
      logs a warning, and returns stage="complete" with debate=None and QA/verification intact.

Run:
  python tests/test_orchestrator.py
or:
  pytest tests/test_orchestrator.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import MAX_MESSAGE_LENGTH, DEBATE_RETRIEVAL_TOP_K
from models import DebateResult, CriticResult
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
        then final stage is "complete" with verification and populated debate (using wider top_k chunks).
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

    mock_debate_chunks = [
        {
            "id": f"chunk_00{i}",
            "text": f"Statutory text for chunk {i}...",
            "metadata": {"section": str(i), "title": f"Title {i}"},
        }
        for i in range(1, DEBATE_RETRIEVAL_TOP_K + 1)
    ]

    mock_debate_result = DebateResult(
        plaintiff_argument="The consumer has a clear right to remedy under Section 35.",
        plaintiff_cited_sections=["35"],
        defense_argument="The seller is protected by statutory exceptions under Section 87.",
        defense_cited_sections=["87"],
        is_grey_zone=True,
        judge_summary="There is a genuine statutory ambiguity between Section 35 and Section 87.",
        clearly_supported_side=None,
    )

    mock_critic_result = CriticResult(
        approved=True,
        final_answer=mock_verification["final_answer"],
        critique_notes="Audit passed with calibrated answers.",
        flagged_grey_zone_conflict=False,
    )

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
        }

        mock_intake = MockIntakeSession.return_value
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
        mock_retrieve.return_value = mock_debate_chunks
        mock_run_debate.return_value = mock_debate_result
        mock_critic.return_value = mock_critic_result

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

        # Confirm debate retrieval was called with DEBATE_RETRIEVAL_TOP_K and NOT QA's chunks
        mock_retrieve.assert_called_once()
        call_args, call_kwargs = mock_retrieve.call_args
        assert call_kwargs.get("top_k") == DEBATE_RETRIEVAL_TOP_K
        assert len(mock_debate_chunks) == DEBATE_RETRIEVAL_TOP_K
        assert mock_debate_chunks != mock_qa_result["retrieved_chunks"]

        # Confirm run_debate was called with the WIDER top_k chunks, not QA's chunks
        mock_run_debate.assert_called_once_with(
            mock_intake.to_case_brief.return_value,
            mock_debate_chunks,
        )
        assert mock_run_debate.call_args[0][1] == mock_debate_chunks
        assert mock_run_debate.call_args[0][1] != mock_qa_result["retrieved_chunks"]

        # Confirm debate field is populated on the returned OrchestratorStageResult
        assert res3["debate"] is not None
        assert res3.debate == mock_debate_result
        assert res3["debate"]["is_grey_zone"] is True
        assert res3["debate"]["judge_summary"] == mock_debate_result.judge_summary

        # Confirm critic was called with (case_brief, verification, debate_result)
        mock_critic.assert_called_once_with(
            mock_intake.to_case_brief.return_value,
            mock_verification,
            mock_debate_result,
        )
        assert res3["critic"] is not None
        assert res3.critic == mock_critic_result
        assert res3["critic"]["approved"] is True

    print("  Test 2 passed: full multi-turn intake flow to complete QA, verification, debate, and critic.")


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
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

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
        mock_retrieve.return_value = []
        mock_run_debate.return_value = None
        mock_critic.return_value = None

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

        # Verification that QA, citation verification, debate, and critic were called
        mock_qa.assert_called_once()
        mock_verify.assert_called_once()
        mock_retrieve.assert_called_once()
        mock_run_debate.assert_called_once()
        mock_critic.assert_called_once()

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
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

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
        mock_retrieve.return_value = []
        mock_run_debate.return_value = None
        mock_critic.return_value = None

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
        # Verify QA, verification, debate, and critic were run on proceed
        mock_qa.assert_called_once()
        mock_verify.assert_called_once()
        mock_retrieve.assert_called_once()
        mock_run_debate.assert_called_once()
        mock_critic.assert_called_once()
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


def test_message_length_limit_enforced():
    """
    Verify MAX_MESSAGE_LENGTH is strictly enforced in start() and answer_question():
    - Messages over the limit return stage 'message_too_long' without calling any LLM function (call count 0).
    - Messages under the limit proceed normally.
    """
    # 1. start() with message exceeding MAX_MESSAGE_LENGTH
    session = CaseSession()
    long_first_message = "X" * (MAX_MESSAGE_LENGTH + 1)

    with patch("orchestrator.understand_query") as mock_understand:
        res1 = session.start(long_first_message)
        assert res1["stage"] == "message_too_long"
        assert f"Please keep your message under {MAX_MESSAGE_LENGTH} characters" in res1["message"]
        # LLM / understand_query must NOT be called
        assert mock_understand.call_count == 0

    # 2. start() with valid message under MAX_MESSAGE_LENGTH proceeds normally
    with patch("orchestrator.understand_query") as mock_understand:
        mock_understand.return_value = {"domain": "unclear", "facts": {}}
        res2 = session.start("A short problem description")
        assert res2["stage"] == "unclear_domain"
        assert mock_understand.call_count == 1

    # 3. answer_question() with answer exceeding MAX_MESSAGE_LENGTH
    session_intake = CaseSession()
    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = {
            "field_key": "what_went_wrong",
            "question_text": "What went wrong with the laptop?",
        }

        # Start session into intake_question state
        r_start = session_intake.start("My laptop is broken")
        assert r_start["stage"] == "intake_question"

        # Provide over-length answer
        long_answer = "Y" * (MAX_MESSAGE_LENGTH + 50)
        r_ans = session_intake.answer_question("what_went_wrong", long_answer)

        assert r_ans["stage"] == "message_too_long"
        assert f"Please keep your message under {MAX_MESSAGE_LENGTH} characters" in r_ans["message"]
        # Downstream intake recording and QA LLM must NOT be called
        assert mock_intake.record_answer.call_count == 0
        assert mock_qa.call_count == 0


def test_debate_exception_does_not_crash_orchestrator():
    """
    (5) If run_debate raises an exception (e.g. Gemini quota limit / API failure),
    the orchestrator catches it specifically, logs a warning, and sets debate=None on
    the final OrchestratorStageResult without crashing the pipeline. QA and citation
    verification results remain fully intact.
    """
    session = CaseSession()

    mock_qa_result = {
        "answer": "Under Section 35, you may file a complaint.",
        "cited_sections": ["35"],
        "status": "answered",
        "retrieved_chunks": [{"metadata": {"section": "35"}, "text": "Section 35 text"}],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Under Section 35, you may file a complaint.",
    }

    wider_chunks = [
        {"id": f"chunk_{i}", "text": f"text {i}", "metadata": {"section": str(i)}}
        for i in range(DEBATE_RETRIEVAL_TOP_K)
    ]

    mock_critic_result = CriticResult(
        approved=True,
        final_answer=mock_verification["final_answer"],
        critique_notes="Critic completed without debate.",
        flagged_grey_zone_conflict=False,
    )

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Smartphone"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = None
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Smartphone"},
            "ready": True,
        }
        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification
        mock_retrieve.return_value = wider_chunks
        mock_critic.return_value = mock_critic_result

        # Simulate a Gemini API quota / rate-limit failure in debate
        mock_run_debate.side_effect = RuntimeError("ResourceExhausted: 429 Resource has been exhausted (e.g. check quota).")

        result = session.start("My smartphone battery exploded.")

        # Pipeline must complete successfully despite debate failure
        assert result["stage"] == "complete"
        assert result.stage == "complete"
        assert result["verified"] is True
        assert result["final_answer"] == mock_verification["final_answer"]
        assert result["verified_sections"] == ["35"]
        assert result["rejected_sections"] == []
        assert result["debate"] is None
        assert result.debate is None
        assert result["critic"] is not None
        assert result.critic == mock_critic_result
        assert session.state == "complete"
        assert session.final_result == mock_verification

        mock_run_debate.assert_called_once()
        mock_verify.assert_called_once()
        # Critic must still be called even when debate resulted in None
        mock_critic.assert_called_once_with(
            mock_intake.to_case_brief.return_value,
            mock_verification,
            None,
        )

    print("  Test 5 passed: debate exception handled gracefully without crashing orchestrator.")


def test_critic_exception_does_not_crash_orchestrator():
    """
    (6) If run_final_critique raises an exception (e.g. Gemini quota limit / API failure),
    the orchestrator catches it specifically, logs a warning, and sets critic=None on
    the final OrchestratorStageResult without crashing the pipeline. The underlying
    verified answer remains completely intact.
    """
    session = CaseSession()

    mock_qa_result = {
        "answer": "Under Section 35, you may file a complaint.",
        "cited_sections": ["35"],
        "status": "answered",
        "retrieved_chunks": [{"metadata": {"section": "35"}, "text": "Section 35 text"}],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["35"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Under Section 35, you may file a complaint.",
    }

    wider_chunks = [
        {"id": f"chunk_{i}", "text": f"text {i}", "metadata": {"section": str(i)}}
        for i in range(DEBATE_RETRIEVAL_TOP_K)
    ]

    mock_debate_result = DebateResult(
        is_grey_zone=False,
        judge_summary="Clear right.",
    )

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = None
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Laptop"},
            "ready": True,
        }
        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification
        mock_retrieve.return_value = wider_chunks
        mock_run_debate.return_value = mock_debate_result

        # Simulate a Gemini API quota error in critic
        mock_critic.side_effect = RuntimeError("ResourceExhausted: 429 Critic LLM quota exhausted.")

        result = session.start("My laptop is completely broken.")

        # Pipeline must complete successfully despite critic failure
        assert result["stage"] == "complete"
        assert result.stage == "complete"
        assert result["verified"] is True
        assert result["final_answer"] == mock_verification["final_answer"]
        assert result["verified_sections"] == ["35"]
        assert result["rejected_sections"] == []
        assert result["debate"] == mock_debate_result
        assert result["critic"] is None
        assert result.critic is None
        assert session.state == "complete"
        assert session.final_result == mock_verification

        mock_critic.assert_called_once()
        mock_verify.assert_called_once()

    print("  Test 6 passed: critic exception handled gracefully without crashing orchestrator.")


def test_critic_revision_with_unverified_citation_is_discarded():
    """
    (7) Regression test for Known Issue #10 (real-API run confirmed 2/3 times via
    validate_critic_real.py): the Critic Agent can rewrite the verified answer to
    weave in a section number (here, "84") that was never checked by Citation
    Verification - typically because it only ever surfaced via the Debate
    Mechanism's separate, wider-top_k retrieval. The orchestrator must catch this
    via reverify_answer_citations() and fail safe by discarding the Critic's
    revision, delivering the pre-critic verified answer instead, and reporting
    critic_revision_discarded=True rather than silently letting the unaudited
    citation reach the citizen.
    """
    session = CaseSession()

    mock_qa_result = {
        "answer": "Under Section 83, you may claim relief.",
        "cited_sections": ["83"],
        "status": "answered",
        "retrieved_chunks": [{"metadata": {"section": "83"}, "text": "Section 83 text about liability."}],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["83"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Under Section 83, you may claim relief. (This answer reflects the Act as of 2026-08-06.)",
    }

    # Debate's wider retrieval surfaces Section 84 - but it is NEVER passed
    # through Citation Verification, matching the real bug's root cause.
    wider_chunks = [
        {"id": "chunk_84", "text": "Section 84 text about manufacturing defects.", "metadata": {"section": "84"}},
    ]

    mock_debate_result = DebateResult(
        is_grey_zone=True,
        judge_summary="Whether Section 84 (manufacturing defect) applies is unsettled.",
    )

    # The Critic weaves the Debate's Section 84 reference into its revision -
    # exactly what was observed in the real validate_critic_real.py runs.
    mock_critic_result = CriticResult(
        approved=False,
        final_answer=(
            "Under Section 83, you may claim relief, conditioned on proving the defect "
            "under Section 84. (This answer reflects the Act as of 2026-08-06.)"
        ),
        critique_notes="Softened to reflect grey-zone uncertainty.",
        flagged_grey_zone_conflict=True,
    )

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic:

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Espresso machine"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = None
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Espresso machine"},
            "ready": True,
        }
        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification
        mock_retrieve.return_value = wider_chunks
        mock_run_debate.return_value = mock_debate_result
        mock_critic.return_value = mock_critic_result

        result = session.start("My espresso machine's boiler burst.")

        assert result["stage"] == "complete"
        # The Critic's revision must be discarded - the pre-critic, fully
        # verified answer is delivered instead, and the discard is reported
        # rather than silently swallowed.
        assert result["final_answer"] == mock_verification["final_answer"]
        assert "84" not in result["final_answer"]
        assert result["verified_sections"] == ["83"]
        assert result["critic_revision_discarded"] is True
        assert result.critic_revision_discarded is True
        # The raw critic result is still surfaced for audit/debugging purposes,
        # even though its revision wasn't used as the delivered final_answer.
        assert result["critic"] == mock_critic_result

    print("  Test 7 passed: Critic revision with an unverified citation is discarded, pre-critic answer delivered.")


def test_critic_revision_with_verified_citation_is_delivered():
    """
    (8) Counterpart to Test 7: when the Critic's revision cites ONLY sections
    that re-verification confirms (against the combined QA + Debate chunk pool),
    the revision IS delivered as final_answer, with verified_sections/rejected_sections
    updated to reflect the freshly re-audited state - and critic_revision_discarded
    stays False.
    """
    session = CaseSession()

    mock_qa_result = {
        "answer": "Under Section 83, you may claim relief.",
        "cited_sections": ["83"],
        "status": "answered",
        "retrieved_chunks": [{"metadata": {"section": "83"}, "text": "Section 83 text about liability."}],
    }

    mock_verification = {
        "verified": True,
        "verified_sections": ["83"],
        "rejected_sections": [],
        "details": {},
        "final_answer": "Under Section 83, you may claim relief. (This answer reflects the Act as of 2026-08-06.)",
    }

    # This time Section 84 IS genuinely present in the Debate's retrieval pool
    # and will pass re-verification's LLM support check.
    wider_chunks = [
        {"id": "chunk_84", "text": "Section 84 text about manufacturing defects.", "metadata": {"section": "84"}},
    ]

    mock_debate_result = DebateResult(
        is_grey_zone=True,
        judge_summary="Whether Section 84 (manufacturing defect) applies is unsettled.",
    )

    critic_revised_answer = (
        "Under Section 83, you may claim relief, conditioned on proving the defect "
        "under Section 84. (This answer reflects the Act as of 2026-08-06.)"
    )
    mock_critic_result = CriticResult(
        approved=False,
        final_answer=critic_revised_answer,
        critique_notes="Softened to reflect grey-zone uncertainty.",
        flagged_grey_zone_conflict=True,
    )

    mock_reverify_response = json.dumps({"is_supported": True, "reason": "Text genuinely supports the claim."})

    with patch("orchestrator.understand_query") as mock_understand, \
         patch("orchestrator.IntakeSession") as MockIntakeSession, \
         patch("orchestrator.answer_question") as mock_qa, \
         patch("orchestrator.verify_citations") as mock_verify, \
         patch("orchestrator.retrieve") as mock_retrieve, \
         patch("orchestrator.run_debate") as mock_run_debate, \
         patch("orchestrator.run_final_critique") as mock_critic, \
         patch("citation_verification_agent.call_llm_structured", return_value=mock_reverify_response):

        mock_understand.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Espresso machine"},
        }
        mock_intake = MockIntakeSession.return_value
        mock_intake.next_question.return_value = None
        mock_intake.run_final_check.return_value = None
        mock_intake.to_case_brief.return_value = {
            "domain": "Consumer Protection",
            "facts": {"what_was_bought_or_hired": "Espresso machine"},
            "ready": True,
        }
        mock_qa.return_value = mock_qa_result
        mock_verify.return_value = mock_verification
        mock_retrieve.return_value = wider_chunks
        mock_run_debate.return_value = mock_debate_result
        mock_critic.return_value = mock_critic_result

        result = session.start("My espresso machine's boiler burst.")

        assert result["stage"] == "complete"
        assert result["final_answer"] == critic_revised_answer
        assert set(result["verified_sections"]) == {"83", "84"}
        assert result["critic_revision_discarded"] is False

    print("  Test 8 passed: Critic revision with a genuinely re-verified citation is delivered as-is.")


if __name__ == "__main__":
    print("\nRunning CaseSession Orchestrator Unit Tests:")
    test_unclear_domain_stops_immediately()
    test_full_multi_turn_flow()
    test_checklist_full_skips_straight_to_complete()
    test_final_check_gap_surfaced_once()
    test_debate_exception_does_not_crash_orchestrator()
    test_critic_exception_does_not_crash_orchestrator()
    test_critic_revision_with_unverified_citation_is_discarded()
    test_critic_revision_with_verified_citation_is_delivered()
    test_answer_question_without_start_raises()
    test_message_length_limit_enforced()
    print("\nAll CaseSession Orchestrator tests passed successfully!")