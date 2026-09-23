import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import query_understanding
from query_understanding import understand_query, EXTRACTION_PROMPT_TEMPLATE, DOMAIN_CHECKLISTS, _build_checklist_summary
from llm_client import call_llm_structured

variants = [
    (
        "Original adv_v2_03",
        "I work as an assembly line technician in an automobile battery manufacturing plant. While handling an industrial acid degreaser solution, the liquid splashed and caused chemical burns to my arms. The specific bottle handed to me on the shop floor had no warning label attached to it. However, the chemical manufacturer had supplied detailed chemical safety data sheets and warning manuals to my corporate employer when delivering the bulk drums to the factory. Can I hold the chemical manufacturer liable under Section 84 for failure to provide adequate warnings to me as the worker?"
    ),
    (
        "Variant A (Shift away from factory/assembly to product user at workplace)",
        "While using an acid degreaser chemical solution at my workplace, the liquid splashed and caused chemical burns to my arms. The bottle I was using had no warning label attached. However, the chemical manufacturer had supplied detailed safety data sheets and warning manuals to my employer when selling them the product. Can I hold the product manufacturer liable under Section 84 of the Consumer Protection Act for failure to provide adequate warnings to me as the user?"
    ),
    (
        "Variant B (Explicitly mentioning consumer product liability / defective product)",
        "I suffered severe chemical burns from a defective chemical cleaner product provided for cleaning at work. The container had no warning labels, but the manufacturer claims they gave safety manuals to the commercial buyer who purchased the chemicals. Under consumer product liability law, can I bring a claim against the manufacturer under Section 84 for inadequate warnings?"
    ),
    (
        "Variant C (Framed around commercial product buyer and employee user)",
        "A commercial chemical product purchased by my employer caused chemical burns to my skin because the container lacked warning labels. The manufacturer argues they provided instructions to the employer. Does product liability under Section 84 apply to protect an employee using a product bought by a company?"
    )
]

print("=" * 80)
print("TESTING DOMAIN CLASSIFICATION ON PHRASING VARIANTS")
print("=" * 80)

domain_list = ", ".join(DOMAIN_CHECKLISTS.keys())
checklist_summary = _build_checklist_summary()

for label, msg in variants:
    print(f"\n--- {label} ---")
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        domain_list=domain_list,
        checklist_summary=checklist_summary,
        user_message=msg,
    )
    raw_response = call_llm_structured(prompt)
    print(f"Raw LLM Response:\n{raw_response.strip()}")
    try:
        parsed = json.loads(raw_response)
        domain = parsed.get("domain")
        print(f"-> Parsed Domain: '{domain}'")
    except Exception as e:
        print(f"-> JSON parse error: {e}")

print("\n" + "=" * 80)
