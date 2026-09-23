"""
Diagnostic Script for Debugging Single Case Retrieval and QA

Runs ONLY the retrieval + QA stage (bypassing full CaseSession):
1. Loads a case by ID from data/eval/labeled_cases_v2_strict.json
2. Extracts facts from case['intake_answers']
3. Calls _build_query_from_facts(facts)
4. Calls retrieve(query, top_k=QA_RETRIEVAL_TOP_K)
5. Calls qa_agent.answer_question(...) directly
6. Prints:
   - Constructed query string
   - Top-k retrieved chunks (section number + title + 100-char snippet)
   - Evaluation of whether expected_cited_sections appear in retrieved chunks
   - QA Agent's raw JSON response (pre-verification)
   - Retrieval miss vs QA reasoning miss diagnosis

Usage:
  python scripts/debug_single_case.py case_04
  python scripts/debug_single_case.py case_05
  python scripts/debug_single_case.py case_06
  python scripts/debug_single_case.py case_07
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure src/ is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import config
from config import QA_RETRIEVAL_TOP_K
from pii_redaction import redact_pii
from qa_agent import _build_query_from_facts, answer_question
import qa_agent
from retrieve import retrieve

logging.basicConfig(level=logging.WARNING)


def debug_case(case_id: str, top_k: int = 10):
    eval_file = PROJECT_ROOT / "data" / "eval" / "labeled_cases_v2_strict.json"
    if not eval_file.exists():
        print(f"Error: Dataset not found at {eval_file}")
        sys.exit(1)

    with open(eval_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    target_case = next((c for c in cases if c.get("id") == case_id), None)
    if not target_case:
        print(f"Error: Case ID '{case_id}' not found in dataset.")
        print(f"Available IDs: {[c.get('id') for c in cases]}")
        sys.exit(1)

    import os
    os.environ["QA_RETRIEVAL_TOP_K"] = str(top_k)

    print("=" * 80)
    print(f"DEBUGGING SINGLE CASE: {case_id} (top_k={top_k})")
    print(f"Citizen Message:\n  \"{target_case.get('citizen_message')}\"")
    expected_sections = target_case.get("expected_cited_sections", [])
    print(f"Expected Cited Sections: {expected_sections}")
    print("=" * 80)

    # 1. Facts and Query Construction
    facts = target_case.get("intake_answers", {})
    query = _build_query_from_facts(facts)
    print(f"\n[1] CONSTRUCTED QUERY STRING:\n  \"{query}\"")

    # 2. Retrieval Stage
    chunks = retrieve(query, top_k=top_k)
    print(f"\n[2] TOP-{len(chunks)} RETRIEVED CHUNKS:")

    retrieved_sections = []
    for idx, ch in enumerate(chunks, 1):
        meta = ch.get("metadata", {})
        sec = meta.get("section", "Unknown")
        title = meta.get("title", "No Title")
        text = ch.get("text", "").replace("\n", " ").strip()
        snippet = text[:100] + ("..." if len(text) > 100 else "")
        retrieved_sections.append(sec)
        print(f"  Chunk {idx}: Section {sec} | Title: {title}")
        print(f"    Snippet: \"{snippet}\"")
        print(f"    Distance: {ch.get('distance')}")

    # Section overlap check
    print("\n[3] RETRIEVAL OVERLAP ANALYSIS:")
    retrieved_sec_clean = [str(s).lower().replace("section", "").strip() for s in retrieved_sections]
    matches_found = []
    for exp in expected_sections:
        exp_clean = str(exp).lower().replace("section", "").strip()
        # Check exact or base match
        exp_base = exp_clean.split("(")[0]
        hit = any(
            r == exp_clean or r.startswith(exp_clean) or exp_clean.startswith(r) or r.split("(")[0] == exp_base
            for r in retrieved_sec_clean
        )
        matches_found.append((exp, hit))
        status = "FOUND in top-k" if hit else "NOT FOUND in top-k"
        print(f"  - Expected '{exp}': {status}")

    any_retrieval_hit = any(hit for _, hit in matches_found)

    # 3. QA Agent Stage (Intercept raw LLM response)
    raw_llm_json_str = None
    orig_call_llm = qa_agent.call_llm_structured

    def _spy_call_llm(prompt: str) -> str:
        nonlocal raw_llm_json_str
        raw_llm_json_str = orig_call_llm(prompt)
        return raw_llm_json_str

    qa_agent.call_llm_structured = _spy_call_llm

    case_brief = {
        "domain": target_case.get("expected_domain", "Consumer Protection"),
        "facts": facts,
        "ready": True,
    }

    try:
        qa_result = answer_question(case_brief)
    finally:
        qa_agent.call_llm_structured = orig_call_llm

    print("\n[4] QA AGENT RAW JSON RESPONSE (Pre-verification):")
    print(raw_llm_json_str)

    print("\n[5] PARSED QA RESULT:")
    print(f"  Status: {qa_result.get('status')}")
    print(f"  Answer: {qa_result.get('answer')}")
    print(f"  Cited Sections: {qa_result.get('cited_sections')}")
    print(f"  Raw Proposed Sections: {qa_result.get('qa_raw_proposed_sections')}")

    print("\n[6] DIAGNOSTIC SUMMARY:")
    if not any_retrieval_hit:
        print(f"  ==> RETRIEVAL MISS: None of the expected sections {expected_sections} were retrieved in top-{top_k}.")
        print("      The failure originates in retrieval/query construction.")
    else:
        print(f"  ==> RETRIEVAL HIT: At least one expected section was retrieved in top-{top_k}.")
        if not qa_result.get("cited_sections"):
            print("      ==> BUG IN QA REASONING / PROMPT: The relevant section chunk was present in context,")
            print("          but QA returned status='unclear' or cited_sections=[]!")
        else:
            print(f"      QA proposed sections: {qa_result.get('cited_sections')}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug single case retrieval + QA")
    parser.add_argument("case_id", help="Case ID to debug (e.g. case_04)")
    parser.add_argument("--top-k", type=int, default=10, help="Retrieval top-k (default: 10)")
    args = parser.parse_args()
    debug_case(args.case_id, top_k=args.top_k)
