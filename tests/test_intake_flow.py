"""
Proves the Intake Agent's checklist logic works correctly, without
needing a real API key. Mocks call_llm_structured so we can test the
STATE MACHINE (which question gets asked, when it stops) independently
of actual LLM extraction quality.

Run: python3 src/test_intake_flow.py
"""

import json
from unittest.mock import patch
from intake_agent import IntakeSession
from domain_checklists import DOMAIN_CHECKLISTS


def test_asks_questions_in_checklist_order():
    session = IntakeSession(domain="Consumer Protection", known_facts={})

    q1 = session.next_question()
    assert q1["field_key"] == "what_was_bought_or_hired", f"Expected first field, got {q1}"
    print(f"  Q1 correctly asked first: '{q1['question_text']}'")

    session.record_answer("what_was_bought_or_hired", "A washing machine")

    q2 = session.next_question()
    assert q2["field_key"] == "what_went_wrong", f"Expected second field, got {q2}"
    print(f"  Q2 correctly asked second: '{q2['question_text']}'")


def test_skips_already_known_facts():
    known = {
        "what_was_bought_or_hired": "A washing machine",
        "what_went_wrong": "It arrived broken",
    }
    session = IntakeSession(domain="Consumer Protection", known_facts=known)

    q = session.next_question()
    assert q["field_key"] == "when_it_happened", f"Should skip known fields, got {q}"
    print(f"  Correctly skipped 2 known fields, asked: '{q['question_text']}'")


def test_completes_when_checklist_full():
    known = {
        "what_was_bought_or_hired": "A washing machine",
        "what_went_wrong": "It arrived broken",
        "when_it_happened": "3 weeks ago",
        "amount_paid": "18000 rupees",
        "seller_or_provider": "XYZ Appliances online",
    }
    session = IntakeSession(domain="Consumer Protection", known_facts=known)

    q = session.next_question()
    assert q is None, f"Expected no more questions, got {q}"
    assert session.is_ready() is True
    print("  Correctly recognized checklist as complete, stopped asking")


def test_max_questions_safety_valve():
    session = IntakeSession(domain="Consumer Protection", known_facts={})
    for _ in range(10):
        q = session.next_question()
        if q is None:
            break
        session.record_answer(q["field_key"], "some answer")

    assert session.questions_asked <= 6, f"Safety valve failed: {session.questions_asked} questions asked"
    print(f"  Safety valve held: stopped at {session.questions_asked} questions")


def test_final_check_uses_mocked_llm():
    known = {
        "what_was_bought_or_hired": "A washing machine",
        "what_went_wrong": "It arrived broken",
        "when_it_happened": "3 weeks ago",
        "amount_paid": "18000 rupees",
        "seller_or_provider": "XYZ Appliances online",
    }
    session = IntakeSession(domain="Consumer Protection", known_facts=known)
    assert session.is_ready() is True

    mock_response = json.dumps({"missing_critical_info": "Whether a replacement was offered"})
    with patch("intake_agent.call_llm_structured", return_value=mock_response):
        gap = session.run_final_check()

    assert gap == "Whether a replacement was offered"
    print(f"  Final check correctly surfaced: '{gap}'")


def test_case_brief_shape():
    known = {"what_was_bought_or_hired": "A washing machine"}
    session = IntakeSession(domain="Consumer Protection", known_facts=known)
    brief = session.to_case_brief()

    assert brief["domain"] == "Consumer Protection"
    assert brief["facts"] == known
    assert brief["ready"] is False
    print(f"  Case brief shape correct: {brief}")


if __name__ == "__main__":
    tests = [
        test_asks_questions_in_checklist_order,
        test_skips_already_known_facts,
        test_completes_when_checklist_full,
        test_max_questions_safety_valve,
        test_final_check_uses_mocked_llm,
        test_case_brief_shape,
    ]
    for t in tests:
        print(f"\n{t.__name__}:")
        t()
    print("\nAll intake state-machine tests passed.")