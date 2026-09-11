"""
Real-API Validation for Debate Mechanism.

NOT mocked - uses the real Gemini API key and live vector retrieval from ChromaDB.
Calls retrieve() for statutory provisions relevant to a realistic dispute,
runs run_debate() end-to-end, and prints the full output:
  - Plaintiff Argument & Cited Sections
  - Defense Argument & Cited Sections
  - Adjudication Verdict: is_grey_zone, clearly_supported_side, judge_summary

Note on Privacy (PII Protection):
  In compliance with repo standards, NO citizen case_brief facts or citizen-derived
  query text are printed to logs or stdout.

Run:
  python scripts/validate_debate_real.py
"""

import json
import sys
from pathlib import Path

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from debate_mechanism import run_debate
from retrieve import retrieve


def run_debate_validation():
    print("=" * 80)
    print("NyayaSetu Real-API Debate Mechanism Validation")
    print("=" * 80)

    # Realistic Consumer Protection dispute involving product defect vs statutory alteration exception
    sample_case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Commercial Espresso Coffee Machine",
            "what_went_wrong": (
                "The boiler unit burst during normal operation causing kitchen damage. "
                "The manufacturer denied product liability compensation, asserting the purchaser "
                "serviced the valve using non-OEM third-party parts, thereby triggering statutory exceptions "
                "for product modification and unauthorized alteration."
            ),
            "amount_paid": "180,000 INR",
            "seller_or_provider": "Apex Commercial Appliances Pvt Ltd",
            "when_it_happened": "3 months post delivery",
            "resolution_attempted": "Written notice demanding replacement and damages sent to manufacturer",
        },
        "ready": True,
    }

    # Focus retrieval on statutory concepts of defect, product liability, and exceptions
    search_query = "product liability defect manufacturer exception alteration misuse deficiency in service"
    retrieved_chunks = retrieve(search_query, top_k=8)

    print(f"\n[Retrieval Summary]")
    print(f"Total statutory chunks retrieved: {len(retrieved_chunks)}")
    for i, c in enumerate(retrieved_chunks, 1):
        meta = c.get("metadata", {})
        sec = meta.get("section", "Unknown")
        title = meta.get("title", "")
        print(f"  Chunk {i}: Section {sec} ({title})")

    print("\nExecuting run_debate() with live Gemini LLM (Plaintiff, Defense, Judge calls)...")
    debate_result = run_debate(sample_case_brief, retrieved_chunks)

    print("\n" + "=" * 80)
    print("LEGAL DEBATE & ADJUDICATION REPORT")
    print("=" * 80)

    print("\n--- [1. PLAINTIFF ADVOCATE POSITION] ---")
    print(f"Cited Sections: {debate_result.get('plaintiff_cited_sections')}")
    print(f"Argument:\n{debate_result.get('plaintiff_argument')}")

    print("\n--- [2. DEFENSE ADVOCATE POSITION] ---")
    print(f"Cited Sections: {debate_result.get('defense_cited_sections')}")
    print(f"Argument:\n{debate_result.get('defense_argument')}")

    print("\n--- [3. IMPARTIAL JUDICIAL ADJUDICATION] ---")
    print(f"Is Grey Zone:           {debate_result.get('is_grey_zone')}")
    print(f"Clearly Supported Side: {debate_result.get('clearly_supported_side')}")
    print(f"Judge's Summary & Legal Evaluation:\n{debate_result.get('judge_summary')}")

    print("\n" + "=" * 80)
    print("Validation Run Complete.")
    print("=" * 80)


if __name__ == "__main__":
    run_debate_validation()
