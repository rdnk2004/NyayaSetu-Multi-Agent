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
import logging
import re
from typing import Any

from llm_client import call_llm_structured, safe_parse_llm_json
from models import CitationVerificationResult, CitationVerificationDetail, QAResult
from pii_redaction import redact_pii

logger = logging.getLogger(__name__)

UNVERIFIED_FALLBACK_ANSWER = (
    "The legal citations in the generated answer could not be verified against the official "
    "statutory provisions. The situation remains unclear and requires manual legal review."
)


def _normalize_section(sec: str) -> str:
    """Normalize a statutory section string for comparative matching."""
    s = re.sub(r"(?i)section\s*", "", str(sec or "")).strip()
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _sections_are_compatible(cited: str, chunk_sec: str) -> bool:
    """
    Check if a cited section matches or is compatible with a retrieved chunk's section.
    Supports:
      - Exact normalized match (e.g. '35' == '35', '2(11)' == '2(11)')
      - Sub-clause / parent matches (e.g. cited '39(1)' matches chunk '39',
        or cited '86(d)' matches chunk '86', or cited '38' matches chunk '38(2)')
      - Clause prefixes (e.g. cited '2(47)(viii)' matches chunk '2(47)')
    Guarantees that distinct definition clauses under Section 2 do NOT cross-match
    (e.g. '2(11)' will never match '2(10)'), and distinct subsections do not cross-match
    (e.g. '38(2)' will never match '38(7)').
    """
    norm_cited = _normalize_section(cited)
    norm_chunk = _normalize_section(chunk_sec)

    if not norm_cited or not norm_chunk:
        return False

    if norm_cited == norm_chunk:
        return True

    base_cited = norm_cited.split("(")[0]
    base_chunk = norm_chunk.split("(")[0]
    if base_cited != base_chunk:
        return False

    # Definitions section (Section 2) has distinct enumerated clauses
    if base_cited == "2":
        if "(" not in norm_chunk or "(" not in norm_cited:
            return True
        return norm_cited.startswith(norm_chunk) or norm_chunk.startswith(norm_cited)

    # For other substantive sections (e.g. 38, 39, 84, 86):
    if "(" not in norm_cited or "(" not in norm_chunk:
        return True

    return norm_cited.startswith(norm_chunk) or norm_chunk.startswith(norm_cited)

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
Note: the QA Agent's answer may combine multiple legal points, each supported by a DIFFERENT cited section. Your task is ONLY to check whether THIS section's text supports the specific claim(s) that would reasonably be attributed to Section {section} - not the entire answer. It is normal and expected for other parts of the answer to be grounded in other, separately-cited sections instead. Do NOT reject this citation merely because this section's text doesn't cover the whole answer - only reject it if this section's text fails to support the portion of the answer that actually relates to it.

Respond ONLY with a JSON object in this exact format:
{{
  "is_supported": true,
  "reason": "<brief justification>"
}}
"""


def _check_section_support(section: str, section_text: str, answer: str) -> tuple[bool, str]:
    """Call LLM to check if the chunk text genuinely supports the answer's claims.

    Returns:
        tuple[bool, str]: (is_supported, reason) where `reason` is the LLM's brief justification.
                          When `is_supported` is False, the reason is also logged for auditability.
    """
    prompt = CITATION_VERIFICATION_PROMPT_TEMPLATE.format(
        section=section,
        section_text=section_text,
        answer=answer,
    )
    raw_response = call_llm_structured(prompt)
    fallback = {
        "is_supported": False,
        "reason": "Failed to parse LLM verification response",
    }
    parsed = safe_parse_llm_json(raw_response, fallback)
    is_supported = bool(parsed.get("is_supported", False))
    reason = str(parsed.get("reason", "")).strip()

    # Log unsupported sections with the LLM's explanation for diagnosability/auditability.
    if not is_supported:
        logger.warning(
            "Citation verification: section '%s' not supported by text. Reason: %s",
            section,
            redact_pii(reason) if reason else "<no reason provided by model>",
        )

    return is_supported, reason


def verify_citations(
    qa_result: QAResult | dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
) -> CitationVerificationResult:
    """
    Verify all citations in the QA Agent's result against retrieved chunks.

    Args:
        qa_result: Output from QA Agent ({"answer": str, "cited_sections": list[str], "status": str})
        retrieved_chunks: List of chunk dicts from retrieve() (each with 'metadata' and 'text')

    Returns:
        CitationVerificationResult: {
            "verified": bool,
            "verified_sections": list[str],
            "rejected_sections": list[str],
            "details": dict[str, dict[str, Any]],
            "final_answer": str
        }
    """
    answer = qa_result.get("answer", "")
    cited_sections = qa_result.get("cited_sections", [])

    if not cited_sections:
        logger.warning("Citation verification: answer has no cited sections to verify.")
        return CitationVerificationResult(
            verified=False,
            verified_sections=[],
            rejected_sections=[],
            details={},
            final_answer=answer if qa_result.get("status") == "unclear" else UNVERIFIED_FALLBACK_ANSWER,
        )

    verified_sections: list[str] = []
    rejected_sections: list[str] = []
    details: dict[str, Any] = {}

    for section in cited_sections:
        sec_str = str(section).strip()

        # 1. Section match in retrieved_chunks (exact or granularity-compatible)
        matching_chunks = [
            chunk for chunk in retrieved_chunks
            if _sections_are_compatible(sec_str, chunk.get("metadata", {}).get("section", ""))
            or _sections_are_compatible(sec_str, chunk.get("section", ""))
        ]

        if not matching_chunks:
            # Section wasn't actually retrieved
            logger.warning(
                "Citation verification: cited section '%s' not found in retrieved chunks.",
                sec_str,
            )
            rejected_sections.append(sec_str)
            details[sec_str] = CitationVerificationDetail(
                supported=False,
                reason="Section not found in retrieved chunks.",
            )
            continue

        # Combine text of all matching chunks for this section
        combined_text = "\n\n".join(
            chunk.get("text", "").strip() for chunk in matching_chunks if chunk.get("text")
        )

        if not combined_text.strip():
            logger.warning(
                "Citation verification: cited section '%s' has empty chunk text.",
                sec_str,
            )
            rejected_sections.append(sec_str)
            details[sec_str] = CitationVerificationDetail(
                supported=False,
                reason="Retrieved chunk text is empty for section.",
            )
            continue

        # 2. LLM semantic support check
        is_supported, reason = _check_section_support(sec_str, combined_text, answer)

        details[sec_str] = CitationVerificationDetail(
            supported=is_supported,
            reason=reason,
        )

        if is_supported:
            verified_sections.append(sec_str)
        else:
            rejected_sections.append(sec_str)

    all_verified = (
        len(rejected_sections) == 0
        and len(verified_sections) == len(cited_sections)
        and len(cited_sections) > 0
    )

    return CitationVerificationResult(
        verified=all_verified,
        verified_sections=verified_sections,
        rejected_sections=rejected_sections,
        details=details,
        final_answer=answer if all_verified else UNVERIFIED_FALLBACK_ANSWER,
    )

