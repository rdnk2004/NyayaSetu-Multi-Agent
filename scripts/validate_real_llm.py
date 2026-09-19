"""
Real-API validation - NOT a unit test, no mocks. Uses your actual
Gemini key to check extraction quality, JSON reliability, and citation
strictness on realistic messy input, before orchestration wiring starts.

Updated to cover Known Issue #3 (specific_legal_question field): checks
both that Query Understanding can extract it from free text, and that
populating it actually changes the QA Agent's retrieval query and
results versus leaving it blank - not just that nothing crashes.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from query_understanding import understand_query
from intake_agent import IntakeSession
from qa_agent import answer_question, _build_query_from_facts
from citation_verification_agent import verify_citations

SAMPLE_MESSAGES = [
    "I bought a washing machine online 3 weeks ago for 18000 rupees and it arrived with a cracked drum. The seller is ignoring my emails.",
    "Hired a photographer for my sister's wedding, paid 40000 advance, he never showed up on the day.",
    "My phone contract renewed automatically without telling me and now they're charging extra.",
    # New: explicitly states a specific legal question, to check Query
    # Understanding actually extracts specific_legal_question from free text.
    "I bought an espresso machine for 180000 INR and the boiler burst after 3 months. "
    "Can I get a full refund, or am I only entitled to a repair?",
]

print("=" * 70)
print("PART A: Query Understanding - real extraction on messy input")
print("=" * 70)
for msg in SAMPLE_MESSAGES:
    result = understand_query(msg)
    print(f"\nInput: {msg}")
    print(f"  -> domain: {result['domain']}")
    print(f"  -> facts: {result['facts']}")
    if "specific_legal_question" in result["facts"]:
        print(f"  -> specific_legal_question extracted: '{result['facts']['specific_legal_question']}'")

print("\n" + "=" * 70)
print("PART B: Intake final check - real LLM 'anything missing?' pass")
print("=" * 70)
complete_facts = {
    "what_was_bought_or_hired": "Washing machine",
    "what_went_wrong": "Arrived with cracked drum",
    "when_it_happened": "3 weeks ago",
    "amount_paid": "18000 rupees",
    "seller_or_provider": "Online seller, name unclear",
    "specific_legal_question": "Am I entitled to a full refund or only a repair?",
}
session = IntakeSession(domain="Consumer Protection", known_facts=complete_facts)
print(f"Checklist complete: {session.is_ready()}")
gap = session.run_final_check()
print(f"Final check flagged: {gap}")

print("\n" + "=" * 70)
print("PART C: QA Agent + Citation Verification - WITH specific_legal_question")
print("=" * 70)
case_brief_with_q = {"domain": "Consumer Protection", "facts": complete_facts, "ready": True}
built_query_with_q = _build_query_from_facts(complete_facts)
print(f"Built retrieval query: \"{built_query_with_q}\"")
qa_result_with_q = answer_question(case_brief_with_q)
print(f"\nQA status: {qa_result_with_q['status']}")
print(f"QA answer: {qa_result_with_q['answer']}")
print(f"QA cited sections: {qa_result_with_q['cited_sections']}")
print(f"Chunks retrieved: {len(qa_result_with_q['retrieved_chunks'])}")

verification_with_q = verify_citations(qa_result_with_q, qa_result_with_q["retrieved_chunks"])
print(f"\nVerification result: {verification_with_q['verified']}")
print(f"Verified sections: {verification_with_q['verified_sections']}")
print(f"Rejected sections: {verification_with_q['rejected_sections']}")
print(f"Final answer shown to user: {verification_with_q['final_answer']}")

print("\n" + "=" * 70)
print("PART D: Same case, WITHOUT specific_legal_question (pre-Known-Issue-#3 behavior)")
print("=" * 70)
facts_without_q = {k: v for k, v in complete_facts.items() if k != "specific_legal_question"}
case_brief_without_q = {"domain": "Consumer Protection", "facts": facts_without_q, "ready": True}
built_query_without_q = _build_query_from_facts(facts_without_q)
print(f"Built retrieval query: \"{built_query_without_q}\"")
qa_result_without_q = answer_question(case_brief_without_q)
print(f"\nQA status: {qa_result_without_q['status']}")
print(f"QA answer: {qa_result_without_q['answer']}")
print(f"QA cited sections: {qa_result_without_q['cited_sections']}")
print(f"Chunks retrieved: {len(qa_result_without_q['retrieved_chunks'])}")

verification_without_q = verify_citations(qa_result_without_q, qa_result_without_q["retrieved_chunks"])
print(f"\nVerification result: {verification_without_q['verified']}")
print(f"Verified sections: {verification_without_q['verified_sections']}")

print("\n" + "=" * 70)
print("PART C vs D comparison:")
print(f"  Query WITH specific_legal_question:    \"{built_query_with_q}\"")
print(f"  Query WITHOUT specific_legal_question: \"{built_query_without_q}\"")
print(f"  Cited sections WITH:    {qa_result_with_q['cited_sections']}")
print(f"  Cited sections WITHOUT: {qa_result_without_q['cited_sections']}")
print("  (Known Issue #3 predicts these should differ - WITHOUT should drift")
print("   toward generic/topically-adjacent sections rather than the specific")
print("   provision the citizen is actually asking about.)")
print("=" * 70)

print("\n" + "=" * 70)
print("Done. Check above for: garbled JSON, invented facts not in the")
print("input, wrong domain guesses, citations rejected that shouldn't be,")
print("and whether specific_legal_question actually changed retrieval focus.")
print("=" * 70)