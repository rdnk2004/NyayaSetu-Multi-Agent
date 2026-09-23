"""
Eval Leakage Checker

Scans an eval dataset (default: data/eval/labeled_cases.json or _v2.json)
for statutory section numbers that appear in citizen-facing input fields
(citizen_message, intake_answers.specific_legal_question) and also appear
in that case's expected_cited_sections ground truth.

Why this matters: `_build_query_from_facts()` in qa_agent.py concatenates
`specific_legal_question` directly into the retrieval query. If that field
already names the section the answer is supposed to cite, the benchmark is
partly graded on whether the system can copy a number back to you rather
than on whether retrieval + reasoning actually finds it. Real citizens do
not phrase their situation as "...is this covered under Section 39?" -- they
describe what happened and ask what they can do about it.

Usage:
    python scripts/check_eval_leakage.py
    python scripts/check_eval_leakage.py --file data/eval/labeled_cases_v2.json
    python scripts/check_eval_leakage.py --strict   # exit 1 if any leak found

This is meant to run as a lightweight CI/pre-flight check before trusting
any evaluation run's numbers -- add it to the same discipline as the
non-determinism warning in run_evaluation.py: don't trust a benchmark score
without first confirming the benchmark isn't leaking its own answers.
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Matches "Section 39", "Sec. 84", "S. 39(1)", "Sections 82, 83 and 84"
# Intentionally looser than citation_verification_agent's extractor: for a
# leakage CHECK we want high recall (better to over-flag and let a human
# dismiss a false positive than to silently miss a real leak).
_SECTION_MENTION_RE = re.compile(
    r"(?i)\b(?:section|sec\.?|s\.)\s*(\d+[A-Za-z]?(?:\(\d+\))?(?:\([a-z]+\))?)"
)


def _normalize(sec: str) -> str:
    s = re.sub(r"(?i)section\s*", "", str(sec or "")).strip()
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _base(sec_norm: str) -> str:
    return sec_norm.split("(")[0]


def _mentions_in(text: str) -> set[str]:
    return {_normalize(m.group(1)) for m in _SECTION_MENTION_RE.finditer(text or "")}


def check_case(case: dict) -> dict:
    expected = case.get("expected_cited_sections", [])
    expected_norm = {_normalize(e) for e in expected}
    expected_base = {_base(e) for e in expected_norm}

    message = case.get("citizen_message", "")
    question = case.get("intake_answers", {}).get("specific_legal_question", "")

    findings = {}
    for field_name, text in (("citizen_message", message), ("specific_legal_question", question)):
        mentioned = _mentions_in(text)
        # Flag both exact and base-section leaks (e.g. mentioning "39" when
        # expected is "39(1)" is still a leak for retrieval-query purposes).
        leaked = {m for m in mentioned if m in expected_norm or _base(m) in expected_base}
        if leaked:
            findings[field_name] = sorted(leaked)

    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        default=str(PROJECT_ROOT / "data" / "eval" / "labeled_cases.json"),
        help="Path to the eval dataset JSON to check.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 if any leakage is found (for CI use).",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Error: dataset not found at {path}")
        sys.exit(2)

    cases = json.loads(path.read_text(encoding="utf-8"))

    total = len(cases)
    leaking = 0
    print("=" * 80)
    print(f"Eval Leakage Check: {path.name} ({total} cases)")
    print("=" * 80)

    for case in cases:
        findings = check_case(case)
        if findings:
            leaking += 1
            print(f"\n[LEAK] {case.get('id')} ({case.get('case_type')})")
            for field, sections in findings.items():
                print(f"    {field}: names section(s) {sections} which are in expected_cited_sections")
        else:
            print(f"[clean] {case.get('id')}")

    print("\n" + "-" * 80)
    print(f"Summary: {leaking}/{total} cases leak an expected section into a citizen-facing field.")
    print("-" * 80)

    if leaking and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()