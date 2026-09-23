import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from query_understanding import understand_query

eval_file = PROJECT_ROOT / "data" / "eval" / "labeled_cases_v2_strict.json"
with open(eval_file, "r", encoding="utf-8") as f:
    cases = json.load(f)

test_case_ids = ["case_01", "case_02", "case_03", "case_08", "case_12"]
selected = [c for c in cases if c["id"] in test_case_ids]

print("=" * 80)
print(f"REGRESSION CHECK: DOMAIN CLASSIFICATION ON {len(selected)} STANDARD CASES")
print("=" * 80)

for c in selected:
    cid = c["id"]
    msg = c["citizen_message"]
    expected_domain = c.get("expected_domain", "Consumer Protection")
    res = understand_query(msg)
    domain = res.get("domain")
    facts_count = len(res.get("facts", {}))
    is_match = domain == expected_domain
    status = "OK" if is_match else "FAILED"
    print(f"[{status}] {cid}: expected '{expected_domain}', got '{domain}' (extracted {facts_count} facts)")
    if not is_match:
        print(f"   Facts: {res.get('facts')}")

print("=" * 80)
