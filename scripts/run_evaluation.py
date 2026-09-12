"""
NyayaSetu Evaluation Runner

Executes end-to-end benchmark evaluation using the REAL Gemini API and ChromaDB.
Evaluates:
  1. Pipeline Question-Answering & Citation Verification
  2. Statutory Citation Grounding & Accuracy
  3. Rejection / Hallucination Rate Proxy
  4. Debate Mechanism Grey-Zone Detection on Ambiguous Cases

Usage:
  python scripts/run_evaluation.py
"""

import datetime
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Ensure src/ is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import builtins
_orig_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _orig_print(*args, **kwargs)

import config
from config import DEBATE_RETRIEVAL_TOP_K
from debate_mechanism import run_debate
from llm_client import _DEFAULT_SESSION_GUARD
from orchestrator import CaseSession
from qa_agent import _build_query_from_facts
from retrieve import retrieve

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluation_runner")


def _normalize_section_token(sec: str) -> str:
    """Normalize a statutory section string for comparative matching."""
    s = re.sub(r"(?i)section\s*", "", str(sec or "")).strip()
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _matches_section(actual: str, expected: str) -> bool:
    """
    Checks if an actual cited section matches an expected section.
    Supports exact matches, subsection matches (e.g. '87(1)' matches '87' and vice versa),
    and clause matches (e.g. '2(47)' matches '2(47)(viii)').
    """
    norm_act = _normalize_section_token(actual)
    norm_exp = _normalize_section_token(expected)

    if not norm_act or not norm_exp:
        return False

    if norm_act == norm_exp:
        return True

    # Base section matching (e.g. '87' vs '87(1)' or '2(11)' vs '2')
    base_act = norm_act.split("(")[0]
    base_exp = norm_exp.split("(")[0]

    if base_act == base_exp:
        # If one is just the base section (e.g. '87' or '34'), allow match
        if "(" not in norm_act or "(" not in norm_exp:
            return True
        # If both have parenthetical clauses, check prefix matching
        if norm_act.startswith(norm_exp) or norm_exp.startswith(norm_act):
            return True

    return False


def _check_citation_overlap(actual_sections: list[str], expected_sections: list[str]) -> bool:
    """Returns True if at least one actual section matches any expected section."""
    for act in actual_sections:
        for exp in expected_sections:
            if _matches_section(act, exp):
                return True
    return False


def run_evaluation():
    eval_file = PROJECT_ROOT / "data" / "eval" / "labeled_cases.json"
    if not eval_file.exists():
        print(f"Error: Dataset not found at {eval_file}")
        sys.exit(1)

    with open(eval_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print("=" * 80)
    print(f"NyayaSetu Benchmark Evaluation Runner ({len(cases)} Cases)")
    print(f"Target Domain: Consumer Protection Act, 2019")
    print(f"Model: {config.GEMINI_MODEL} | Max Budget: {config.MAX_CALLS_PER_SESSION} calls")
    print("=" * 80)

    results = []
    unrun_cases = []
    total_cases = len(cases)

    total_citations_generated = 0
    total_citations_rejected = 0

    ambiguous_total = 0
    ambiguous_correct = 0

    verified_and_matched_count = 0

    start_time = time.time()

    for idx, case in enumerate(cases, 1):
        case_id = case.get("id", f"case_{idx:02d}")
        case_type = case.get("case_type", "clear_cut")
        expected_sections = case.get("expected_cited_sections", [])
        intake_answers = case.get("intake_answers", {})

        # Safety valve: check remaining session budget headroom
        estimated_calls = 7 if case_type == "ambiguous" else 4
        current_calls = _DEFAULT_SESSION_GUARD.session_call_count
        max_calls = config.MAX_CALLS_PER_SESSION

        if current_calls + estimated_calls > max_calls:
            print("\n" + "!" * 80)
            print(f"[BUDGET GUARD] Approaching MAX_CALLS_PER_SESSION ceiling: {current_calls}/{max_calls} calls.")
            print(f"Halting evaluation before executing {case_id} to ensure clean safety shutdown.")
            unrun_cases = [c["id"] for c in cases[idx - 1 :]]
            print(f"Cases NOT run in this batch ({len(unrun_cases)}): {unrun_cases}")
            print("!" * 80)
            break

        print(f"\n[{idx}/{total_cases}] Evaluating {case_id} ({case_type})...")

        # 1. Run Pipeline via CaseSession
        session = CaseSession()
        stage_result = session.start(case["citizen_message"])

        # Auto-fill intake questions from pre-configured dataset answers
        intake_turns = 0
        while stage_result.stage == "intake_question" and intake_turns < 10:
            intake_turns += 1
            field = stage_result.field_key
            # Fetch answer from test case, or fallback to generic realistic context
            answer = intake_answers.get(field, f"Standard details provided for {field}")
            stage_result = session.answer_question(field, answer)

        # Handle final check gap if surfaced
        if stage_result.stage == "final_check_gap":
            stage_result = session.proceed()

        # Extract pipeline outputs
        is_verified = bool(stage_result.verified)
        verified_sections = list(stage_result.verified_sections or [])
        rejected_sections = list(stage_result.rejected_sections or [])
        final_answer = str(stage_result.final_answer or "")

        all_citations = verified_sections + rejected_sections
        total_citations_generated += len(all_citations)
        total_citations_rejected += len(rejected_sections)

        # Evaluate citation match
        has_matched_citation = _check_citation_overlap(verified_sections, expected_sections)
        passed_verification_and_match = is_verified and has_matched_citation
        if passed_verification_and_match:
            verified_and_matched_count += 1

        # 2. Debate Mechanism Adjudication for Ambiguous Cases
        debate_data = None
        is_grey_zone_matched = None

        if case_type == "ambiguous":
            ambiguous_total += 1
            try:
                case_brief = session.intake_session.to_case_brief()
                search_query = _build_query_from_facts(case_brief.get("facts", {}))
                debate_chunks = retrieve(search_query, top_k=DEBATE_RETRIEVAL_TOP_K)
                debate_result = run_debate(case_brief, debate_chunks)

                is_grey_zone = bool(debate_result.get("is_grey_zone", False))
                # For ambiguous cases, expected outcome is is_grey_zone == True
                is_grey_zone_matched = is_grey_zone is True
                if is_grey_zone_matched:
                    ambiguous_correct += 1

                debate_data = {
                    "is_grey_zone": is_grey_zone,
                    "clearly_supported_side": debate_result.get("clearly_supported_side"),
                    "judge_summary": debate_result.get("judge_summary", "")[:200] + "...",
                    "plaintiff_cited_sections": debate_result.get("plaintiff_cited_sections", []),
                    "defense_cited_sections": debate_result.get("defense_cited_sections", []),
                    "matched_ambiguity_label": is_grey_zone_matched,
                }
            except Exception as e:
                logger.error(f"Error executing debate for {case_id}: {e}")
                debate_data = {"error": str(e), "matched_ambiguity_label": False}

        case_record = {
            "id": case_id,
            "case_type": case_type,
            "verified": is_verified,
            "expected_sections": expected_sections,
            "verified_sections": verified_sections,
            "rejected_sections": rejected_sections,
            "citation_match": has_matched_citation,
            "passed_full_verification": passed_verification_and_match,
            "debate": debate_data,
        }
        results.append(case_record)

        status_flag = "PASS" if passed_verification_and_match else "FAIL"
        print(f"  Result: [{status_flag}] | Verified: {is_verified} | Sections: {verified_sections} (Expected: {expected_sections})")
        if debate_data:
            print(f"  Debate Grey-Zone Adjudication: {debate_data.get('is_grey_zone')} (Match: {debate_data.get('matched_ambiguity_label')})")

    duration = time.time() - start_time
    executed_count = len(results)

    # 3. Compute Metrics
    grounding_accuracy = (verified_and_matched_count / executed_count * 100) if executed_count else 0.0
    rejection_rate = (total_citations_rejected / total_citations_generated * 100) if total_citations_generated else 0.0
    grey_zone_accuracy = (ambiguous_correct / ambiguous_total * 100) if ambiguous_total else 0.0

    print("\n" + "=" * 80)
    print("EVALUATION BENCHMARK METRICS SUMMARY")
    print("=" * 80)
    print(f"Total Cases Tested:                      {executed_count} / {total_cases}")
    print(f"Total LLM API Calls Consumed:            {_DEFAULT_SESSION_GUARD.session_call_count}")
    print(f"Execution Duration:                      {duration:.2f}s")
    print("-" * 80)
    print(f"Citation Grounding & Match Rate:         {grounding_accuracy:.1f}% ({verified_and_matched_count}/{executed_count})")
    print(f"Citation Rejection (Hallucination Proxy): {rejection_rate:.1f}% ({total_citations_rejected}/{total_citations_generated})")
    print(f"Grey-Zone Detection Accuracy (Ambiguous):{grey_zone_accuracy:.1f}% ({ambiguous_correct}/{ambiguous_total})")
    print("=" * 80)

    # 4. Save Detailed Results File
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "data" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"results_{timestamp}.json"

    payload = {
        "timestamp": timestamp,
        "model": config.GEMINI_MODEL,
        "duration_seconds": round(duration, 2),
        "total_cases_evaluated": executed_count,
        "total_cases_available": total_cases,
        "api_calls_used": _DEFAULT_SESSION_GUARD.session_call_count,
        "metrics": {
            "grounding_and_match_rate_pct": round(grounding_accuracy, 1),
            "citation_rejection_rate_pct": round(rejection_rate, 1),
            "grey_zone_detection_accuracy_pct": round(grey_zone_accuracy, 1),
        },
        "unrun_cases": unrun_cases,
        "cases": results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\nDetailed evaluation results saved to: {out_file}")
    return payload


if __name__ == "__main__":
    run_evaluation()
