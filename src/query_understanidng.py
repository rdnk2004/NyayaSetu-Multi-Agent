"""
Query Understanding Agent

Takes the citizen's raw first message and does ONE pass over it:
  - guesses which legal domain it falls under
  - pulls out whatever facts are already stated, mapped onto that
    domain's checklist field keys
  - leaves everything else blank for the Intake Agent to ask about

This is a single LLM call with a structured (JSON) output - it does
NOT ask follow-up questions itself, that's the Intake Agent's job.
"""

import json
from domain_checklists import DOMAIN_CHECKLISTS
from llm_client import call_llm_structured


EXTRACTION_PROMPT_TEMPLATE = """You are a legal intake assistant. A citizen has described \
their situation in plain language. Your job has two parts:

1. Decide which ONE of these legal domains it best fits: {domain_list}
   If it doesn't clearly fit any of them, set domain to "unclear".

2. Extract ONLY facts the citizen actually stated. For the domain's \
checklist fields below, fill in a value ONLY if it was explicitly \
mentioned. Leave a field as null if it wasn't mentioned - do NOT guess \
or infer facts that weren't said.

Checklist fields for each domain:
{checklist_summary}

Citizen's message:
\"\"\"{user_message}\"\"\"

Respond with ONLY a JSON object, no other text, in this exact shape:
{{
  "domain": "<one of {domain_list} or 'unclear'>",
  "facts": {{ "<field_key>": "<value or null>", ... }}
}}
"""


def _build_checklist_summary() -> str:
    lines = []
    for domain, checklist in DOMAIN_CHECKLISTS.items():
        field_keys = [f["key"] for f in checklist["fields"]]
        lines.append(f"- {domain}: {', '.join(field_keys)}")
    return "\n".join(lines)


def understand_query(user_message: str) -> dict:
    """
    Returns:
        {
          "domain": str,          # e.g. "Consumer Protection" or "unclear"
          "facts": dict,          # {field_key: value_or_None, ...}
        }
    """
    domain_list = ", ".join(DOMAIN_CHECKLISTS.keys())
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        domain_list=domain_list,
        checklist_summary=_build_checklist_summary(),
        user_message=user_message,
    )

    raw_response = call_llm_structured(prompt)

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        # Fail safe rather than silently guessing - matches the
        # blueprint's "never hallucinate" principle: if we can't
        # parse a clean structured answer, don't pretend we understood.
        return {"domain": "unclear", "facts": {}}

    domain = parsed.get("domain", "unclear")
    facts = parsed.get("facts", {})
    # Drop any null/empty values so downstream code only sees real facts
    facts = {k: v for k, v in facts.items() if v}

    return {"domain": domain, "facts": facts}