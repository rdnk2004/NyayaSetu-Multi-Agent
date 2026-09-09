"""
Real-API Validation for Landmark Case Agent.

NOT mocked - uses real Gemini key and the local 'case_law' Chroma collection.
Runs find_landmark_cases() against a realistic Consumer Protection case brief
and prints the full output, including the case titles, courts, dates,
programmatically copied source URLs, attributions, and grounded explanations.

Run:
  python scripts/validate_landmark_case_real.py
"""

import json
import sys
from pathlib import Path

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from landmark_case_agent import find_landmark_cases


def run_landmark_case_validation():
    print("=" * 75)
    print("NyayaSetu Real-API Landmark Case Agent Validation")
    print("=" * 75)

    # Realistic Consumer Protection dispute involving vehicle defects and dealer/manufacturer liability
    sample_case_brief = {
        "domain": "Consumer Protection",
        "facts": {
            "what_was_bought_or_hired": "Luxury Sedan vehicle",
            "what_went_wrong": (
                "The car had continuous sunroof leakage that entered the cabin and damaged "
                "the electronic control unit. Despite multiple workshop visits and repair "
                "attempts, the dealer and manufacturer refused to replace the vehicle or refund the money, "
                "claiming dealer-manufacturer relationship is principal-to-principal."
            ),
            "amount_paid": "4,200,000 INR",
            "seller_or_provider": "Authorized Automobile Dealer and Manufacturer",
            "when_it_happened": "Within 2 months of purchase",
        },
        "ready": True,
    }

    print("\n[Input Case Brief Facts]:")
    for k, v in sample_case_brief["facts"].items():
        print(f"  - {k}: {v}")

    print("\nExecuting find_landmark_cases() with live vector retrieval and Gemini LLM...")
    result = find_landmark_cases(sample_case_brief)

    print("\n" + "=" * 75)
    print(f"Result Status: {result.get('status')}")
    print(f"Total Landmark Cases Retrieved: {len(result.get('cases', []))}")
    print("=" * 75)

    for i, case in enumerate(result.get("cases", []), 1):
        print(f"\n--- [Case {i}] ---")
        print(f"Title:        {case.get('case_title')}")
        print(f"Court:        {case.get('court')}")
        print(f"Date:         {case.get('date')}")
        print(f"Source URL:   {case.get('source_url')}")
        print(f"Attribution:  {case.get('attribution')}")
        print("\nRelevance Explanation:")
        print(f"  {case.get('relevance_explanation')}")

    print("\n" + "=" * 75)
    print("Validation Complete. Please check that:")
    print("  1. Source URLs match valid Indian Kanoon URLs from data/raw/case_law/.")
    print("  2. Explanations are strictly grounded in court holdings (e.g. principal-to-principal liability).")
    print("=" * 75)


if __name__ == "__main__":
    run_landmark_case_validation()
