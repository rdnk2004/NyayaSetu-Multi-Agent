"""
Real-API Validation for CaseSession Orchestrator.

NOT mocked, uses the real Gemini API and local vector store.
Runs one full realistic multi-turn conversation through CaseSession end-to-end:
  start -> read question -> provide realistic answer -> repeat until complete.

Prints every stage transition so it can be manually inspected.

Run:
  python scripts/validate_orchestrator_real.py
"""

import sys
from pathlib import Path

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orchestrator import CaseSession

# Realistic answers prepared for any required/optional checklist field
PRESET_ANSWERS = {
    "amount_paid": "I paid 14,500 rupees online via debit card.",
    "seller_or_provider": "I bought it from Cloudtail Electronics on an online marketplace.",
    "what_was_bought_or_hired": "A top-load washing machine.",
    "what_went_wrong": "It arrived with a cracked drum and leaks water constantly.",
    "when_it_happened": "About 2 weeks ago.",
    "resolution_attempted": "I contacted customer care with photos of the crack, but they rejected my replacement request.",
}


def run_orchestrator_validation():
    print("=" * 70)
    print("NyayaSetu Real-API Orchestrator Validation")
    print("=" * 70)

    # Initial realistic citizen query with some facts present, but seller and price omitted
    first_message = (
        "I bought a microwave online 2 weeks ago and it sparks violently "
        "whenever I turn it on. Customer service is ignoring my emails."
    )

    print(f"\n[Citizen Initial Message]:\n\"{first_message}\"\n")

    session = CaseSession()
    step_result = session.start(first_message)

    turn = 1
    max_turns = 8  # Safety guard for the validation loop

    while turn <= max_turns:
        stage = step_result.get("stage")
        print(f"--- [Stage Transition: '{stage}'] ---")

        if stage == "unclear_domain":
            print(f"Agent requested clarification: {step_result.get('message')}")
            break

        elif stage == "intake_question":
            field_key = step_result["field_key"]
            question_text = step_result["question_text"]
            print(f"\n[Turn {turn}] Question for missing field '{field_key}':")
            print(f"  Agent: \"{question_text}\"")

            answer = PRESET_ANSWERS.get(
                field_key,
                f"Information regarding {field_key.replace('_', ' ')}."
            )
            print(f"  Citizen answers: \"{answer}\"\n")

            step_result = session.answer_question(field_key, answer)
            turn += 1

        elif stage == "final_check_gap":
            gap = step_result.get("gap")
            print(f"\n[Final Check Flagged Potential Gap]:")
            print(f"  Gap: \"{gap}\"")
            print("  Caller action: Proceeding to QA and Citation Verification...\n")
            step_result = session.proceed()

        elif stage == "complete":
            print("\n" + "=" * 70)
            print("CASE RESOLUTION COMPLETE")
            print("=" * 70)
            print(f"Verified against statutory chunks : {step_result.get('verified')}")
            print(f"Verified statutory sections       : {step_result.get('verified_sections')}")
            print(f"Rejected statutory sections       : {step_result.get('rejected_sections')}")
            print("\nFinal Grounded Legal Advice:\n")
            print(step_result.get("final_answer"))
            print("=" * 70)
            break

        else:
            print(f"Unknown stage encountered: {step_result}")
            break

    if turn > max_turns and step_result.get("stage") != "complete":
        print(f"\nWarning: Reached maximum turn limit ({max_turns}) without completing.")


if __name__ == "__main__":
    run_orchestrator_validation()
