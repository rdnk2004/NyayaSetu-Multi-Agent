import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from orchestrator import CaseSession

cases_path = PROJECT_ROOT / "data" / "eval" / "labeled_cases_v2_strict.json"
with open(cases_path, "r", encoding="utf-8") as f:
    all_cases = json.load(f)

target_ids = ["case_04", "case_05", "case_06", "case_07"]
target_cases = [c for c in all_cases if c.get("id") in target_ids]

print(f"Running pipeline for {len(target_cases)} cases with Option A stitched retrieval...\n")

for case in target_cases:
    cid = case["id"]
    msg = case["citizen_message"]
    expected = case.get("expected_cited_sections", [])
    intake_answers = case.get("intake_answers", {})
    
    print("=" * 80)
    print(f"CASE: {cid} | Expected: {expected}")
    
    session = CaseSession()
    stage_result = session.start(msg)
    
    intake_turns = 0
    while stage_result.stage == "intake_question" and intake_turns < 10:
        intake_turns += 1
        field = stage_result.field_key
        answer = intake_answers.get(field, f"Standard details provided for {field}")
        stage_result = session.answer_question(field, answer)

    if stage_result.stage == "final_check_gap":
        stage_result = session.proceed()
        
    print(f"Stage: {stage_result.stage}")
    print(f"QA Raw Proposed: {stage_result.qa_raw_proposed_sections}")
    print(f"Verified Sections: {stage_result.verified_sections}")
    print(f"Rejected Sections: {stage_result.rejected_sections}")
    ans = stage_result.final_answer or ""
    print(f"Final Answer: {ans[:300]}...")
print("=" * 80)
