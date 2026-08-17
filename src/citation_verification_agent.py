"""
Citation Verification Agent

Validates the output of the QA Agent against the retrieved statutory chunks:
1. Verifies that every cited section actually exists in the retrieved chunks.
2. Uses structured LLM evaluation (call_llm_structured) to ensure that the
   retrieved chunk's text genuinely supports the claim made in the answer.
3. Rejects any citation that was not retrieved or is not supported by text.
4. If ANY citation fails verification, reverts final_answer to a safe fallback.
"""

import json
from typing import Any

try:
    from llm_client import call_llm_structured
except ImportError:
    from src.llm_client import call_llm_structured

UNVERIFIED_FALLBACK_ANSWER = (
    "The legal citations in the generated answer could not be verified against the official "
    "statutory provisions. The situation remains unclear and requires manual legal review."
)

CITATION_VERIFICATION_PROMPT_TEMPLATE = """You are a strict legal citation verification auditor for NyayaSetu.
Your task is to verify whether the legal claim made in the QA Agent's answer is genuinely and factually supported by the statutory text from the cited section.

Section Cited: Section {section}

Retrieved Statutory Text:
\"\"\"{section_text}\"\"\"

QA Agent's Answer:
\"\"\"{answer}\"\"\"

Evaluate whether the cited section text actually provides factual and legal support for the relevant statements made in the answer.
Do not assume or extrapolate beyond what the text explicitly states.
If the text does not genuinely support the claim, or if the claim contradicts or misrepresents the text, mark is_supported as false.

Respond ONLY with a JSON object in this exact format:
{{
  "is_supported": true,
  "reason": "<brief justification>"
}}
"""


def _check_section_support(section: str, section_text: str, answer: str) -> tuple[bool, str]:
    """Call LLM to check if the chunk text genuinely supports the answer's claims."""
    prompt = CITATION_VERIFICATION_PROMPT_TEMPLATE.format(
        section=section,
        section_text=section_text,
        answer=answer,
    )
    raw_response = call_llm_structured(prompt)
    try:
        parsed = json.loads(raw_response)
        is_supported = bool(parsed.get("is_supported", False))
        reason = parsed.get("reason", "")
        return is_supported, reason
    except (json.JSONDecodeError, Exception) as e:
        # Safe fallback: fail safe if LLM output cannot be cleanly parsed
        return False, f"Failed to parse LLM verification response: {e}"


def verify_citations(qa_result: dict[str, Any], retrieved_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Verify all citations in the QA Agent's result against retrieved chunks.

    Args:
        qa_result: Output from QA Agent ({"answer": str, "cited_sections": list[str], "status": str})
        retrieved_chunks: List of chunk dicts from retrieve() (each with 'metadata' and 'text')

    Returns:
        {
            "verified": bool,
            "verified_sections": list[str],
            "rejected_sections": list[str],
            "final_answer": str
        }
    """
    answer = qa_result.get("answer", "")
    cited_sections = qa_result.get("cited_sections", [])

    if not cited_sections:
        return {
            "verified": True,
            "verified_sections": [],
            "rejected_sections": [],
            "final_answer": answer,
        }

    verified_sections: list[str] = []
    rejected_sections: list[str] = []

    for section in cited_sections:
        sec_str = str(section).strip()

        # 1. Exact section match in retrieved_chunks
        matching_chunks = [
            chunk for chunk in retrieved_chunks
            if str(chunk.get("metadata", {}).get("section", "")).strip() == sec_str
            or str(chunk.get("section", "")).strip() == sec_str
        ]

        if not matching_chunks:
            # Section wasn't actually retrieved
            rejected_sections.append(sec_str)
            continue

        # Combine text of all matching chunks for this section
        combined_text = "\n\n".join(
            chunk.get("text", "").strip() for chunk in matching_chunks if chunk.get("text")
        )

        if not combined_text.strip():
            rejected_sections.append(sec_str)
            continue

        # 2. LLM semantic support check
        is_supported, _ = _check_section_support(sec_str, combined_text, answer)

        if is_supported:
            verified_sections.append(sec_str)
        else:
            rejected_sections.append(sec_str)

    all_verified = len(rejected_sections) == 0 and len(verified_sections) == len(cited_sections)

    return {
        "verified": all_verified,
        "verified_sections": verified_sections,
        "rejected_sections": rejected_sections,
        "final_answer": answer if all_verified else UNVERIFIED_FALLBACK_ANSWER,
    }
