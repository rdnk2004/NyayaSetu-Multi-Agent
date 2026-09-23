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
  python scripts/run_evaluation.py --resume     # skip cases already completed
                                                  # in the most recent results file
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
from pii_redaction import redact_pii
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


def compute_citation_metrics(
    verified_sections: list[str],
    expected_sections: list[str],
    recall_threshold: float = 0.5,
    precision_threshold: float = 0.5,
    shape_aware_small_set_threshold: float = 0.6,
) -> dict:
    """
    Computes citation precision, recall, and F1 against the full expected_sections set.
    - Matched expected: expected sections that have at least one matching verified section.
    - Matched verified: verified sections that match at least one expected section.
    - Recall: len(matched_expected) / len(expected_sections)
    - Precision: len(matched_verified) / len(verified_sections)
    - Fixed match: (recall >= recall_threshold) and (precision >= precision_threshold)
    - Shape-aware match:
        If len(expected_sections) <= 2, requires recall >= shape_aware_small_set_threshold (0.6, requiring 2/2 or 1/1)
        If len(expected_sections) > 2, requires recall >= recall_threshold (0.5)
        and precision >= precision_threshold
    """
    if not expected_sections:
        rec = 1.0 if not verified_sections else 0.0
        prec = 1.0 if not verified_sections else 0.0
        f1 = 1.0 if not verified_sections else 0.0
        return {
            "recall": rec,
            "precision": prec,
            "f1": f1,
            "matched_expected": [],
            "matched_verified": [],
            "citation_match": rec >= recall_threshold,
            "citation_match_fixed": rec >= recall_threshold,
            "citation_match_shape_aware": rec >= recall_threshold,
            "shape_aware_recall_threshold": recall_threshold,
        }

    matched_expected = [
        exp for exp in expected_sections
        if any(_matches_section(act, exp) for act in verified_sections)
    ]
    matched_verified = [
        act for act in verified_sections
        if any(_matches_section(act, exp) for exp in expected_sections)
    ]

    recall = round(len(matched_expected) / len(expected_sections), 3)
    precision = round(len(matched_verified) / len(verified_sections), 3) if verified_sections else 0.0
    f1 = round((2 * precision * recall) / (precision + recall), 3) if (precision + recall) > 0 else 0.0

    citation_match_fixed = bool(recall >= recall_threshold and precision >= precision_threshold)

    # Shape-aware threshold: prevents 1-of-2 substitutions on small sets while allowing top-k retrieval flexibility on large sets
    shape_aware_recall_thresh = shape_aware_small_set_threshold if len(expected_sections) <= 2 else recall_threshold
    citation_match_shape_aware = bool(recall >= shape_aware_recall_thresh and precision >= precision_threshold)

    return {
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "matched_expected": matched_expected,
        "matched_verified": matched_verified,
        "citation_match": citation_match_fixed,  # primary backward compatible flag
        "citation_match_fixed": citation_match_fixed,
        "citation_match_shape_aware": citation_match_shape_aware,
        "shape_aware_recall_threshold": shape_aware_recall_thresh,
    }


def _check_citation_overlap(actual_sections: list[str], expected_sections: list[str]) -> bool:
    """Legacy helper: Returns True if at least one actual section matches any expected section."""
    for act in actual_sections:
        for exp in expected_sections:
            if _matches_section(act, exp):
                return True
    return False


def _find_latest_results_file(out_dir: Path) -> Path | None:
    """Finds the most recent results_*.json file in out_dir, if any."""
    candidates = sorted(out_dir.glob("results_*.json"))
    return candidates[-1] if candidates else None


def _recompute_totals_from_results(results: list[dict]) -> dict:
    """
    Recomputes all running counters from a list of already-completed case
    records, so a --resume run has correct aggregate metrics without having
    to separately persist/restore counter state.
    """
    total_citations_generated = 0
    total_citations_rejected = 0
    ambiguous_total = 0
    ambiguous_correct = 0
    verified_and_matched_count = 0
    shape_aware_matched_count = 0

    for rec in results:
        verified_sections = rec.get("verified_sections", [])
        rejected_sections = rec.get("rejected_sections", [])
        total_citations_generated += len(verified_sections) + len(rejected_sections)
        total_citations_rejected += len(rejected_sections)

        if rec.get("passed_full_verification"):
            verified_and_matched_count += 1
        if rec.get("passed_shape_aware_verification"):
            shape_aware_matched_count += 1

        debate = rec.get("debate")
        if rec.get("case_type") == "ambiguous":
            ambiguous_total += 1
            if debate and debate.get("matched_ambiguity_label"):
                ambiguous_correct += 1

    return {
        "total_citations_generated": total_citations_generated,
        "total_citations_rejected": total_citations_rejected,
        "ambiguous_total": ambiguous_total,
        "ambiguous_correct": ambiguous_correct,
        "verified_and_matched_count": verified_and_matched_count,
        "shape_aware_matched_count": shape_aware_matched_count,
    }


def run_evaluation():
    eval_file = PROJECT_ROOT / "data" / "eval" / "labeled_cases_v2_strict.json"
    if "--file" in sys.argv:
        f_idx = sys.argv.index("--file")
        if f_idx + 1 < len(sys.argv):
            eval_file = Path(sys.argv[f_idx + 1])
    elif "-f" in sys.argv:
        f_idx = sys.argv.index("-f")
        if f_idx + 1 < len(sys.argv):
            eval_file = Path(sys.argv[f_idx + 1])

    if not eval_file.is_absolute():
        eval_file = PROJECT_ROOT / eval_file

    if not eval_file.exists():
        print(f"Error: Dataset not found at {eval_file}")
        sys.exit(1)

    with open(eval_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    recall_threshold = 0.5
    precision_threshold = 0.5
    if "--recall-threshold" in sys.argv:
        r_idx = sys.argv.index("--recall-threshold")
        if r_idx + 1 < len(sys.argv):
            recall_threshold = float(sys.argv[r_idx + 1])
    elif any(a.startswith("--recall-threshold=") for a in sys.argv):
        recall_threshold = float([a for a in sys.argv if a.startswith("--recall-threshold=")][0].split("=")[1])

    if "--precision-threshold" in sys.argv:
        p_idx = sys.argv.index("--precision-threshold")
        if p_idx + 1 < len(sys.argv):
            precision_threshold = float(sys.argv[p_idx + 1])
    elif any(a.startswith("--precision-threshold=") for a in sys.argv):
        precision_threshold = float([a for a in sys.argv if a.startswith("--precision-threshold=")][0].split("=")[1])

    print("=" * 80)
    print(f"NyayaSetu Benchmark Evaluation Runner ({len(cases)} Cases)")
    print(f"Target Domain: Consumer Protection Act, 2019")
    print(f"Model: {config.GEMINI_MODEL} | Max Budget: {config.MAX_CALLS_PER_SESSION} calls")
    print(f"Citation Pass Rule (Fixed):       Recall >= {recall_threshold} & Precision >= {precision_threshold}")
    print(f"Citation Pass Rule (Shape-Aware): <=2 sections: Recall >= 0.6 | >2 sections: Recall >= 0.5")
    print("=" * 80)

    # --- Output file set up BEFORE the loop, so incremental saves inside
    # the loop and the final save at the end both write to the same file. ---
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "data" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"results_{timestamp}.json"

    results = []
    unrun_cases = []

    total_citations_generated = 0
    total_citations_rejected = 0
    ambiguous_total = 0
    ambiguous_correct = 0
    verified_and_matched_count = 0
    shape_aware_matched_count = 0

    # --- Resume support: skip cases already completed in the most recent
    # results file, and restore all running totals from those records. ---
    if "--resume" in sys.argv:
        prev_file = _find_latest_results_file(out_dir)
        if prev_file is None:
            print("[RESUME] No prior results_*.json file found — running full set.")
        else:
            with open(prev_file, "r", encoding="utf-8") as f:
                prev_payload = json.load(f)

            prev_results = prev_payload.get("cases", [])
            prev_unrun_ids = set(prev_payload.get("unrun_cases", []))
            done_ids = {c["id"] for c in prev_results}

            # Only re-run cases that were previously unrun/failed; keep
            # completed case records as-is.
            cases = [c for c in cases if c.get("id") in prev_unrun_ids or c.get("id") not in done_ids]
            results = list(prev_results)

            totals = _recompute_totals_from_results(results)
            total_citations_generated = totals["total_citations_generated"]
            total_citations_rejected = totals["total_citations_rejected"]
            ambiguous_total = totals["ambiguous_total"]
            ambiguous_correct = totals["ambiguous_correct"]
            verified_and_matched_count = totals["verified_and_matched_count"]
            shape_aware_matched_count = totals.get("shape_aware_matched_count", 0)

            print(f"[RESUME] Loaded {prev_file.name}: {len(done_ids)} cases already completed.")
            print(f"[RESUME] Re-running {len(cases)} remaining case(s): {[c['id'] for c in cases]}")

    total_cases = len(results) + len(cases)
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
            remaining = [c["id"] for c in cases[idx - 1 :]]
            unrun_cases = list(unrun_cases) + remaining
            print(f"Cases NOT run in this batch ({len(remaining)}): {remaining}")
            print("!" * 80)
            break

        print(f"\n[{len(results) + idx}/{total_cases}] Evaluating {case_id} ({case_type})...")

        # 1. Run Pipeline via CaseSession
        session = CaseSession()

        try:
            stage_result = session.start(case["citizen_message"])

            # Auto-fill intake questions from pre-configured dataset answers
            intake_turns = 0
            while stage_result.stage == "intake_question" and intake_turns < 10:
                intake_turns += 1
                field = stage_result.field_key
                answer = intake_answers.get(field, f"Standard details provided for {field}")
                stage_result = session.answer_question(field, answer)

            if stage_result.stage == "final_check_gap":
                stage_result = session.proceed()

            if case_id == "case_03" and session.intake_session:
                brief = session.intake_session.to_case_brief()
                diag_q = _build_query_from_facts(brief.get("facts", {}))
                print(f"  [DIAGNOSTIC case_03] Constructed Query: \"{redact_pii(diag_q)}\"")
                diag_chunks = retrieve(diag_q, top_k=5)
                diag_secs = [
                    f"Sec {ch.get('metadata', {}).get('section')} ({ch.get('metadata', {}).get('title')})"
                    for ch in diag_chunks
                ]
                print(f"  [DIAGNOSTIC case_03] Retrieved Chunks: {diag_secs}")

        except RuntimeError as e:
            print(f"  [SKIPPED] {case_id}: {e}")
            unrun_cases.append(case_id)
            continue

        # Extract pipeline outputs
        is_verified = bool(stage_result.verified)
        verified_sections = list(stage_result.verified_sections or [])
        rejected_sections = list(stage_result.rejected_sections or [])
        qa_raw_proposed_sections = list(
            getattr(stage_result, "qa_raw_proposed_sections", None)
            or (session.qa_result.get("qa_raw_proposed_sections", []) if hasattr(session, "qa_result") and session.qa_result else [])
            or []
        )
        final_answer = str(stage_result.final_answer or "")

        all_citations = verified_sections + rejected_sections
        total_citations_generated += len(all_citations)
        total_citations_rejected += len(rejected_sections)

        # Evaluate citation match via full expected-set precision / recall
        citation_metrics = compute_citation_metrics(
            verified_sections=verified_sections,
            expected_sections=expected_sections,
            recall_threshold=recall_threshold,
            precision_threshold=precision_threshold,
        )
        has_matched_citation = citation_metrics["citation_match_fixed"]
        passed_verification_and_match = is_verified and has_matched_citation
        if passed_verification_and_match:
            verified_and_matched_count += 1

        passed_shape_aware = is_verified and citation_metrics["citation_match_shape_aware"]
        if passed_shape_aware:
            shape_aware_matched_count += 1

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

        qa_chunks = session.qa_result.get("retrieved_chunks", []) if hasattr(session, "qa_result") and session.qa_result else []
        retrieved_chunk_sections = [
            f"Section {c.get('metadata', {}).get('section', 'Unknown')} ({c.get('metadata', {}).get('title', 'No Title')})"
            for c in qa_chunks
        ]

        case_record = {
            "id": case_id,
            "case_type": case_type,
            "verified": is_verified,
            "expected_sections": expected_sections,
            "retrieved_chunks": retrieved_chunk_sections,
            "qa_raw_proposed_sections": qa_raw_proposed_sections,
            "verified_sections": verified_sections,
            "rejected_sections": rejected_sections,
            "matched_expected_sections": citation_metrics["matched_expected"],
            "matched_verified_sections": citation_metrics["matched_verified"],
            "citation_precision": citation_metrics["precision"],
            "citation_recall": citation_metrics["recall"],
            "citation_f1": citation_metrics["f1"],
            "citation_match": has_matched_citation,
            "passed_full_verification": passed_verification_and_match,
            "citation_match_shape_aware": citation_metrics["citation_match_shape_aware"],
            "passed_shape_aware_verification": passed_shape_aware,
            "final_answer": final_answer,
            "debate": debate_data,
        }
        results.append(case_record)

        # Incremental/partial save after every case, so a crash mid-run
        # doesn't lose already-completed cases or API spend.
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({"cases": results, "unrun_cases": unrun_cases}, f, indent=2)

        status_fixed = "PASS" if passed_verification_and_match else "FAIL"
        status_shape = "PASS" if passed_shape_aware else "FAIL"
        print(f"  Result: [Fixed: {status_fixed} | ShapeAware: {status_shape}] | Verified: {is_verified} | Precision: {citation_metrics['precision']:.2f} | Recall: {citation_metrics['recall']:.2f} | F1: {citation_metrics['f1']:.2f}")
        print(f"  QA Proposed: {qa_raw_proposed_sections} | Verified Secs: {verified_sections} (Expected: {expected_sections})")
        print(f"  Matched Expected: {citation_metrics['matched_expected']} | Matched Verified: {citation_metrics['matched_verified']}")
        print(f"  Retrieved Chunks (post-stitching): {retrieved_chunk_sections}")
        if debate_data:
            print(f"  Debate Grey-Zone Adjudication: {debate_data.get('is_grey_zone')} (Match: {debate_data.get('matched_ambiguity_label')})")

    duration = time.time() - start_time
    executed_count = len(results)

    # 3. Compute Metrics
    grounding_accuracy = (verified_and_matched_count / executed_count * 100) if executed_count else 0.0
    shape_aware_accuracy = (shape_aware_matched_count / executed_count * 100) if executed_count else 0.0
    mean_precision = (sum(r.get("citation_precision", 0.0) for r in results) / executed_count * 100) if executed_count else 0.0
    mean_recall = (sum(r.get("citation_recall", 0.0) for r in results) / executed_count * 100) if executed_count else 0.0
    mean_f1 = (sum(r.get("citation_f1", 0.0) for r in results) / executed_count) if executed_count else 0.0
    rejection_rate = (total_citations_rejected / total_citations_generated * 100) if total_citations_generated else 0.0
    grey_zone_accuracy = (ambiguous_correct / ambiguous_total * 100) if ambiguous_total else 0.0

    print("\n" + "=" * 80)
    print("EVALUATION BENCHMARK METRICS SUMMARY")
    print("=" * 80)
    print(f"Total Cases Tested:                      {executed_count} / {total_cases}")
    print(f"Total LLM API Calls Consumed (this run): {_DEFAULT_SESSION_GUARD.session_call_count}")
    print(f"Execution Duration (this run):           {duration:.2f}s")
    print("-" * 80)
    print("PRIMARY GROUNDING METRICS (Continuous Distributions):")
    print(f"  Mean Citation Precision:               {mean_precision:.1f}%")
    print(f"  Mean Citation Recall:                  {mean_recall:.1f}%")
    print(f"  Mean Citation F1:                      {mean_f1:.3f}")
    print("-" * 80)
    print("SECONDARY PASS RATES (Threshold Sensitivity Analysis):")
    print(f"  Fixed Pass Rate (Rec >= {recall_threshold}, Prec >= {precision_threshold}):         {grounding_accuracy:.1f}% ({verified_and_matched_count}/{executed_count})")
    print(f"  Shape-Aware Pass Rate (<=2: Rec>=0.6, >2: Rec>=0.5): {shape_aware_accuracy:.1f}% ({shape_aware_matched_count}/{executed_count})")
    print("-" * 80)
    print("SUBSYSTEM VERIFICATION DIAGNOSTICS:")
    print(f"  Citation Rejection (Hallucination Proxy): {rejection_rate:.1f}% ({total_citations_rejected}/{total_citations_generated})")
    print(f"  Grey-Zone Detection Accuracy (Ambiguous):{grey_zone_accuracy:.1f}% ({ambiguous_correct}/{ambiguous_total})")
    print("=" * 80)

    # 4. Save Final Detailed Results File (overwrites the partial save above
    # with the complete payload including metrics)
    payload = {
        "timestamp": timestamp,
        "model": config.GEMINI_MODEL,
        "duration_seconds": round(duration, 2),
        "total_cases_evaluated": executed_count,
        "total_cases_available": total_cases,
        "api_calls_used": _DEFAULT_SESSION_GUARD.session_call_count,
        "metrics": {
            "mean_citation_precision_pct": round(mean_precision, 1),
            "mean_citation_recall_pct": round(mean_recall, 1),
            "mean_citation_f1": round(mean_f1, 3),
            "grounding_pass_rate_fixed_pct": round(grounding_accuracy, 1),
            "grounding_pass_rate_shape_aware_pct": round(shape_aware_accuracy, 1),
            "grounding_and_match_rate_pct": round(grounding_accuracy, 1),
            "recall_threshold_fixed": recall_threshold,
            "precision_threshold_fixed": precision_threshold,
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