"""
Real-API validation - NOT a unit test, no mocks. Uses your actual
Gemini key to check extraction quality, JSON reliability, and citation
strictness on realistic messy input, before orchestration wiring starts.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from query_understanding import understand_query
from intake_agent import IntakeSession
from qa_agent import answer_question
from citation_verification_agent import verify_citations

SAMPLE_MESSAGES = [
    "I bought a washing machine online 3 weeks ago for 18000 rupees and it arrived with a cracked drum. The seller is ignoring my emails.",
    "Hired a photographer for my sister's wedding, paid 40000 advance, he never showed up on the day.",
    "My phone contract renewed automatically without telling me and now they're charging extra.",
]

print("=" * 70)
print("PART A: Query Understanding - real extraction on messy input")
print("=" * 70)
for msg in SAMPLE_MESSAGES:
    result = understand_query(msg)
    print(f"\nInput: {msg}")
    print(f"  -> domain: {result['domain']}")
    print(f"  -> facts: {result['facts']}")

print("\n" + "=" * 70)
print("PART B: Intake final check - real LLM 'anything missing?' pass")
print("=" * 70)
complete_facts = {
    "what_was_bought_or_hired": "Washing machine",
    "what_went_wrong": "Arrived with cracked drum",
    "when_it_happened": "3 weeks ago",
    "amount_paid": "18000 rupees",
    "seller_or_provider": "Online seller, name unclear",
}
session = IntakeSession(domain="Consumer Protection", known_facts=complete_facts)
print(f"Checklist complete: {session.is_ready()}")
gap = session.run_final_check()
print(f"Final check flagged: {gap}")

print("\n" + "=" * 70)
print("PART C: QA Agent + Citation Verification - full real chain")
print("=" * 70)
case_brief = {"domain": "Consumer Protection", "facts": complete_facts, "ready": True}
qa_result = answer_question(case_brief)
print(f"\nQA status: {qa_result['status']}")
print(f"QA answer: {qa_result['answer']}")
print(f"QA cited sections: {qa_result['cited_sections']}")
print(f"Chunks retrieved: {len(qa_result['retrieved_chunks'])}")

verification = verify_citations(qa_result, qa_result["retrieved_chunks"])
print(f"\nVerification result: {verification['verified']}")
print(f"Verified sections: {verification['verified_sections']}")
print(f"Rejected sections: {verification['rejected_sections']}")
print(f"Final answer shown to user: {verification['final_answer']}")

print("\n" + "=" * 70)
print("Done. Check above for: garbled JSON, invented facts not in the")
print("input, wrong domain guesses, or citations rejected that shouldn't be.")
print("=" * 70)