"""
Debate Mechanism (Adversarial Statutory Argumentation & Grey-Zone Adjudication)

Implements run_debate(case_brief: dict, retrieved_chunks: list[dict]) -> dict:
1. Two LLM calls represent two opposing advocate positions arguing how the SAME
   retrieved statutory provisions apply to the citizen's case:
   - "plaintiff_side": argues the interpretation most favorable to the citizen.
   - "defense_side": argues the interpretation most favorable to the opposing party.
   - Both arguments must be strictly grounded ONLY in the retrieved chunks.
2. A third LLM call acts as "judge":
   - Adjudicates whether the dispute is a genuine grey zone (statutory ambiguity or
     both interpretations legitimately arguable) or if one side is clearly supported.
   - Determines is_grey_zone, judge_summary, and clearly_supported_side.
3. Fail-safe parsing: Never crashes on malformed JSON; returns a safe fallback.
4. When retrieved_chunks is empty, skips LLM calls entirely and returns safe defaults.
"""

import json
import logging
from typing import Any

from llm_client import call_llm_structured, safe_parse_llm_json

logger = logging.getLogger(__name__)


PLAINTIFF_PROMPT_TEMPLATE = """You are a legal advocate representing the citizen (plaintiff/consumer) under Indian Law. \
A citizen has reported a legal dispute. You are provided with the citizen's facts and retrieved statutory provisions from the relevant Act.

Your task is to construct the strongest possible legal argument in FAVOR of the citizen (plaintiff), arguing for liability, relief, or remedy.

Domain: {domain}

Citizen's Facts:
{facts_text}

Retrieved Statutory Provisions:
{chunks_text}

Rules:
1. Ground your argument ONLY in the text of the retrieved statutory provisions above. Do NOT use outside knowledge, speculate, or invent legal principles.
2. Advance the interpretation most favorable to the citizen (e.g. broader reading of what counts as a deficiency or defect, favoring provider liability).
3. Cite the exact section number(s) (e.g. "Section 2(11)", "Section 35", "Section 84") from the retrieved chunks that support your argument.
4. Do NOT invent facts or cite sections not present in the retrieved chunks.

Respond with ONLY a JSON object, no other text, in this exact format:
{{
  "argument": "<strong legal argument advocating for the citizen/plaintiff grounded strictly in the retrieved text>",
  "cited_sections": ["<exact section number, e.g. Section 2(11)>"]
}}
"""


DEFENSE_PROMPT_TEMPLATE = """You are a legal advocate representing the respondent/opposing party (defense/seller/service provider) under Indian Law. \
A citizen has reported a legal dispute. You are provided with the citizen's facts and retrieved statutory provisions from the relevant Act.

Your task is to construct the strongest possible legal defense in FAVOR of the opposing party (defense), arguing against liability or for statutory exceptions.

Domain: {domain}

Citizen's Facts:
{facts_text}

Retrieved Statutory Provisions:
{chunks_text}

Rules:
1. Ground your argument ONLY in the text of the retrieved statutory provisions above. Do NOT use outside knowledge, speculate, or invent legal principles.
2. Advance the interpretation most favorable to the opposing party (e.g. narrower reading of definitions, statutory exceptions or exclusions such as under Section 87, absence of statutory breach, or procedural non-compliance).
3. Cite the exact section number(s) (e.g. "Section 87", "Section 2(11)") from the retrieved chunks that support your argument.
4. Do NOT invent facts or cite sections not present in the retrieved chunks.

Respond with ONLY a JSON object, no other text, in this exact format:
{{
  "argument": "<strong legal defense advocating for the opposing party grounded strictly in the retrieved text>",
  "cited_sections": ["<exact section number, e.g. Section 87>"]
}}
"""


JUDGE_PROMPT_TEMPLATE = """You are an impartial legal judge adjudicating a dispute under Indian Law. \
You are provided with the citizen's facts, the relevant statutory provisions retrieved from the Act, and arguments from both the Plaintiff (citizen) and Defense (opposing party).

Domain: {domain}

Citizen's Facts:
{facts_text}

Retrieved Statutory Provisions:
{chunks_text}

Plaintiff's Argument:
\"\"\"{plaintiff_argument}\"\"\"
Sections cited by Plaintiff: {plaintiff_citations}

Defense's Argument:
\"\"\"{defense_argument}\"\"\"
Sections cited by Defense: {defense_citations}

Task:
Carefully evaluate both arguments against the actual text of the retrieved statutory provisions.
Determine:
1. Is this a genuine grey zone (the retrieved text is genuinely ambiguous or both readings are legitimately arguable under the law), or is one side clearly correct based on the plain wording and clear statutory mandate of the text?
2. If genuinely ambiguous:
   - Set "is_grey_zone" to true.
   - Set "clearly_supported_side" to null.
   - Provide a plain-language "judge_summary" explaining what exactly is unsettled or disputed between the competing interpretations.
3. If one side is clearly correct based on the text:
   - Set "is_grey_zone" to false.
   - Set "clearly_supported_side" to "plaintiff" or "defense".
   - Provide a plain-language "judge_summary" stating which side the text actually supports and why, citing the specific supporting section(s).

Rules:
- Base your judgment strictly on the retrieved statutory provisions and presented arguments.
- Do NOT introduce outside statutory sections not present in the retrieved text.

Respond with ONLY a JSON object, no other text, in this exact format:
{{
  "is_grey_zone": true,
  "judge_summary": "<plain-language evaluation explaining the ambiguity or why one side is clearly correct, citing section numbers>",
  "clearly_supported_side": null
}}
(Note: If is_grey_zone is false, "clearly_supported_side" must be either "plaintiff" or "defense".)
"""


def _format_facts_for_prompt(facts: dict) -> str:
    """Format the citizen's facts into readable bullet points for the prompt."""
    if not facts or not isinstance(facts, dict):
        return "No specific facts provided."

    lines = []
    for k, v in facts.items():
        if v:
            clean_key = str(k).replace("_", " ").title()
            lines.append(f"- {clean_key}: {v}")

    return "\n".join(lines) if lines else "No specific facts provided."


def _format_chunks_for_prompt(chunks: list[dict]) -> str:
    """Format candidate retrieved chunks with their exact section numbers and text."""
    if not chunks:
        return "No legal chunks retrieved."

    formatted_chunks = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {}) or {}
        section = metadata.get("section") or chunk.get("section", "Unknown")
        title = metadata.get("title", "")
        text = chunk.get("text", "").strip()

        sec_label = section if str(section).lower().startswith("section") else f"Section {section}"
        title_label = f" ({title})" if title else ""

        formatted_chunks.append(
            f"--- Chunk {i} [{sec_label}{title_label}] ---\n{text}"
        )

    return "\n\n".join(formatted_chunks)


def _clean_citations(raw_citations: Any) -> list[str]:
    """Clean and standardize cited sections list."""
    if isinstance(raw_citations, list):
        items = [str(s).strip() for s in raw_citations if str(s).strip()]
    elif isinstance(raw_citations, str) and raw_citations.strip():
        items = [raw_citations.strip()]
    else:
        items = []

    cleaned: list[str] = []
    for s in items:
        sec = s[8:].strip() if s.lower().startswith("section ") else s
        if sec and sec not in cleaned:
            cleaned.append(sec)
    return cleaned


def run_debate(case_brief: dict, retrieved_chunks: list[dict]) -> dict:
    """
    IMPORTANT: retrieved_chunks should be retrieved with a HIGHER top_k
    than QA Agent uses (e.g. top_k=8, not 5). The judge needs visibility
    into adjacent/countervailing provisions to make a well-grounded
    grey-zone determination - a narrow top-5 optimized for direct
    question-answering can hide the exact clause that would resolve
    (or properly complicate) the ambiguity. Confirmed via real-case
    testing: Section 87(1) was missed at top_k=5 despite being directly
    relevant to a modification-defense argument.
    
    Conducts a structured adversarial legal debate between Plaintiff and Defense advocates,
    adjudicated by an impartial Judge, grounded strictly in retrieved statutory chunks.

    Args:
        case_brief: dict shaped like IntakeSession.to_case_brief()
                    ({"domain": str, "facts": dict, "ready": bool})
        retrieved_chunks: list of chunk dicts from retrieve() (each with 'metadata' and 'text')

    Returns:
        dict: {
            "plaintiff_argument": str,
            "plaintiff_cited_sections": list[str],
            "defense_argument": str,
            "defense_cited_sections": list[str],
            "is_grey_zone": bool,
            "judge_summary": str,
            "clearly_supported_side": str | None
        }
    """
    safe_default = {
        "plaintiff_argument": "",
        "plaintiff_cited_sections": [],
        "defense_argument": "",
        "defense_cited_sections": [],
        "is_grey_zone": False,
        "judge_summary": "No relevant statutory provisions were retrieved to conduct a legal debate.",
        "clearly_supported_side": None,
    }

    if not retrieved_chunks or not isinstance(retrieved_chunks, list):
        return safe_default

    if not isinstance(case_brief, dict):
        return {
            **safe_default,
            "judge_summary": "Invalid case brief provided; cannot conduct a legal debate.",
        }

    domain = str(case_brief.get("domain", "Unknown") or "Unknown")
    facts = case_brief.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}

    facts_text = _format_facts_for_prompt(facts)
    chunks_text = _format_chunks_for_prompt(retrieved_chunks)

    # 1. Plaintiff Advocate LLM Call
    plaintiff_prompt = PLAINTIFF_PROMPT_TEMPLATE.format(
        domain=domain,
        facts_text=facts_text,
        chunks_text=chunks_text,
    )
    raw_plaintiff = call_llm_structured(plaintiff_prompt)
    plaintiff_data = safe_parse_llm_json(raw_plaintiff, {})
    if not plaintiff_data:
        return {
            "plaintiff_argument": "",
            "plaintiff_cited_sections": [],
            "defense_argument": "",
            "defense_cited_sections": [],
            "is_grey_zone": False,
            "judge_summary": "Unable to complete legal debate due to an invalid plaintiff argument response.",
            "clearly_supported_side": None,
        }

    plaintiff_argument = str(plaintiff_data.get("argument", "") or "").strip()
    plaintiff_cited_sections = _clean_citations(plaintiff_data.get("cited_sections", []))

    # 2. Defense Advocate LLM Call
    defense_prompt = DEFENSE_PROMPT_TEMPLATE.format(
        domain=domain,
        facts_text=facts_text,
        chunks_text=chunks_text,
    )
    raw_defense = call_llm_structured(defense_prompt)
    defense_data = safe_parse_llm_json(raw_defense, {})
    if not defense_data:
        return {
            "plaintiff_argument": plaintiff_argument,
            "plaintiff_cited_sections": plaintiff_cited_sections,
            "defense_argument": "",
            "defense_cited_sections": [],
            "is_grey_zone": False,
            "judge_summary": "Unable to complete legal debate due to an invalid defense argument response.",
            "clearly_supported_side": None,
        }

    defense_argument = str(defense_data.get("argument", "") or "").strip()
    defense_cited_sections = _clean_citations(defense_data.get("cited_sections", []))

    # 3. Judge Adjudication LLM Call
    plaintiff_citations_str = (
        ", ".join(f"Section {s}" for s in plaintiff_cited_sections)
        if plaintiff_cited_sections
        else "None"
    )
    defense_citations_str = (
        ", ".join(f"Section {s}" for s in defense_cited_sections)
        if defense_cited_sections
        else "None"
    )

    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        domain=domain,
        facts_text=facts_text,
        chunks_text=chunks_text,
        plaintiff_argument=plaintiff_argument,
        plaintiff_citations=plaintiff_citations_str,
        defense_argument=defense_argument,
        defense_citations=defense_citations_str,
    )
    raw_judge = call_llm_structured(judge_prompt)
    judge_data = safe_parse_llm_json(raw_judge, {})
    if not judge_data:
        return {
            "plaintiff_argument": plaintiff_argument,
            "plaintiff_cited_sections": plaintiff_cited_sections,
            "defense_argument": defense_argument,
            "defense_cited_sections": defense_cited_sections,
            "is_grey_zone": False,
            "judge_summary": "Unable to complete legal debate adjudication due to an invalid judge response.",
            "clearly_supported_side": None,
        }

    is_grey_zone = bool(judge_data.get("is_grey_zone", False))
    judge_summary = str(judge_data.get("judge_summary", "") or "").strip()
    if not judge_summary:
        judge_summary = "Legal analysis of the competing statutory interpretations completed."

    clearly_supported_side = None
    if not is_grey_zone:
        raw_side = judge_data.get("clearly_supported_side")
        if raw_side:
            side_str = str(raw_side).strip().lower()
            if side_str in ("plaintiff", "defense"):
                clearly_supported_side = side_str

    return {
        "plaintiff_argument": plaintiff_argument,
        "plaintiff_cited_sections": plaintiff_cited_sections,
        "defense_argument": defense_argument,
        "defense_cited_sections": defense_cited_sections,
        "is_grey_zone": is_grey_zone,
        "judge_summary": judge_summary,
        "clearly_supported_side": clearly_supported_side,
    }
