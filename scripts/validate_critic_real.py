"""
Real-API Validation for Critic Agent & Full Pipeline End-to-End.

NOT mocked - uses the real Gemini API and live ChromaDB vector store.
Runs a realistic ambiguous case through CaseSession end-to-end:
  start -> answer intake questions -> complete (QA + Verification + Debate + Critic).

Prints both the Debate Mechanism adjudication and the Critic Agent's final audit,
allowing manual cross-checking to verify that grey-zone determinations and
answer calibrations align.

Run:
  python scripts/validate_critic_real.py
"""

import sys
from pathlib import Path

# Ensure src is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from orchestrator import CaseSession

# Realistic answers prepared for any intake checklist field
PRESET_ANSWERS = {
    "amount_paid": "180,000 INR paid via bank transfer.",
    "seller_or_provider": "Apex Commercial Appliances Pvt Ltd.",
    "what_was_bought_or_hired": "Commercial Espresso Coffee Machine.",
    "what_went_wrong": (
        "The boiler unit burst during normal operation causing kitchen damage. "
        "The manufacturer denied product liability compensation, asserting I "
        "serviced the valve using non-OEM third-party parts, claiming statutory "
        "exceptions for product modification under Section 87."
    ),
    "when_it_happened": "3 months post delivery.",
    "resolution_attempted": "Written notice demanding replacement and damages sent to manufacturer.",
}


def run_critic_validation():
    print("=" * 80)
    print("NyayaSetu Real-API Critic Agent & Pipeline Validation")
    print("=" * 80)

    # Realistic ambiguous problem description
    first_message = (
        "I bought an espresso coffee machine from Apex Commercial Appliances for 180,000 INR. "
        "The boiler burst causing kitchen damage, but they denied liability because I changed "
        "a valve filter with a third party part."
    )

    print(f"\n[Citizen Initial Message]:\n\"{first_message}\"\n")

    session = CaseSession()
    step_result = session.start(first_message)

    turn = 1
    max_turns = 8

    while turn <= max_turns:
        stage = step_result.get("stage")
        print(f"--- [Stage Transition: '{stage}'] ---")

        if stage == "unclear_domain":
            print(f"Agent requested clarification: {step_result.get('message')}")
            break

        elif stage == "message_too_long":
            print(f"Message exceeds length limit: {step_result.get('message')}")
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
            print("  Caller action: Proceeding to QA, Verification, Debate, and Critic...\n")
            step_result = session.proceed()

        elif stage == "complete":
            print("\n" + "=" * 80)
            print("PIPELINE EXECUTION COMPLETE")
            print("=" * 80)
            print(f"Verified against statutory chunks : {step_result.get('verified')}")
            print(f"Verified statutory sections       : {step_result.get('verified_sections')}")
            print(f"Rejected statutory sections       : {step_result.get('rejected_sections')}")

            # Debate output
            debate = step_result.get("debate")
            print("\n" + "-" * 80)
            print("1. DEBATE MECHANISM ADJUDICATION")
            print("-" * 80)
            if debate:
                print(f"Is Grey Zone           : {debate.get('is_grey_zone')}")
                print(f"Clearly Supported Side : {debate.get('clearly_supported_side')}")
                print(f"Judge Summary          :\n{debate.get('judge_summary')}")
            else:
                print("Debate Result: None (not performed or skipped)")

            # Critic output
            critic = step_result.get("critic")
            print("\n" + "-" * 80)
            print("2. CRITIC AGENT QUALITY AUDIT")
            print("-" * 80)
            if critic:
                print(f"Approved for Citizen   : {critic.get('approved')}")
                print(f"Flagged Grey-Zone Gap  : {critic.get('flagged_grey_zone_conflict')}")
                print(f"Critique Notes         :\n{critic.get('critique_notes')}")
                print(f"\nCritic Final Answer    :\n{critic.get('final_answer')}")
            else:
                print("Critic Result: None (not performed or skipped)")

            # Final Advice delivered
            print("\n" + "=" * 80)
            print("FINAL CITIZEN-FACING LEGAL ADVICE:")
            print("=" * 80)
            print(step_result.get("final_answer"))
            print("=" * 80)
            break

        else:
            print(f"Unknown stage encountered: {step_result}")
            break

    if turn > max_turns and step_result.get("stage") != "complete":
        print(f"\nWarning: Reached maximum turn limit ({max_turns}) without completing.")


if __name__ == "__main__":
    run_critic_validation()
