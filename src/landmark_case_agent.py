"""
Landmark Case Agent (Precedent Case Identification & Grounded Explanation)

Consumes a completed case brief from the Intake Agent:
  - Builds a natural-language query from the collected facts
  - Retrieves candidate precedent cases from the 'case_law' Chroma collection
  - Prompts the LLM via call_llm_structured to generate a 2-3 sentence explanation
    of why each case is relevant, grounded strictly in the court's reasoning
  - Programmatically copies source_url and metadata directly from the retrieved chunk
    (never allowing the LLM to generate or tamper with source URLs)
  - Applies fail-safe error handling to gracefully use fallback explanations if
    LLM output parsing fails
"""

import json
from pathlib import Path

# pyrefly: ignore [missing-import]
from llm_client import call_llm_structured
# pyrefly: ignore [missing-import]
from retrieve_case_law import retrieve_case_law
import logging

logger = logging.getLogger(__name__)

RELEVANCE_PROMPT_TEMPLATE = """You are a legal assistant specializing in Indian case law. \
A citizen has reported a legal dispute. You are provided with the citizen's facts and the \
court's actual reasoning from a precedent case.

Citizen's Facts:
{facts_text}

Precedent Case:
Title: {case_title}
Court: {court}
Date: {date}
Court's Actual Reasoning:
{reasoning_text}

Task:
Write a 2-3 sentence explanation of WHY this precedent case is relevant to the citizen's specific situation.

Rules:
1. Ground your explanation ONLY in the court's actual reasoning provided above.
2. NEVER invent facts or legal holdings that are not present in the provided reasoning text.
3. Keep the explanation clear, objective, and plain-language (2 to 3 sentences).
4. Do NOT output or paraphrase any URLs or external citations.

Respond with ONLY a JSON object, no other text, in this exact format:
{{
  "relevance_explanation": "<2-3 sentence explanation grounded strictly in the reasoning>"
}}
"""


def _build_query_from_facts(facts: dict) -> str:
    """Build a natural-language search query from the citizen's collected facts."""
    if not facts or not isinstance(facts, dict):
        return ""

    parts = []
    for v in facts.values():
        if v is not None:
            v_str = str(v).strip()
            if v_str:
                parts.append(v_str)

    return " ".join(parts)


def _format_facts_for_prompt(facts: dict) -> str:
    """Format the citizen's facts into readable bullet points for the prompt."""
    if not facts:
        return "No specific facts provided."

    lines = []
    for k, v in facts.items():
        if v:
            clean_key = k.replace("_", " ").title()
            lines.append(f"- {clean_key}: {v}")

    return "\n".join(lines) if lines else "No specific facts provided."


def find_landmark_cases(case_brief: dict) -> dict:
    """
    Finds relevant precedent cases and generates grounded relevance explanations.

    Args:
        case_brief: dict shaped like IntakeSession.to_case_brief()
                    ({"domain": str, "facts": dict, "ready": bool})

    Returns:
        dict: {
            "cases": [
                {
                    "case_title": str,
                    "court": str,
                    "date": str,
                    "source_url": str,
                    "attribution": str,
                    "relevance_explanation": str
                }
            ],
            "status": "found" | "no_relevant_cases"
        }
    """
    if not isinstance(case_brief, dict):
        return {"cases": [], "status": "no_relevant_cases"}

    facts = case_brief.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}

    query = _build_query_from_facts(facts)
    if not query:
        return {"cases": [], "status": "no_relevant_cases"}

    retrieved_cases = retrieve_case_law(query, top_k=3)
    if not retrieved_cases:
        return {"cases": [], "status": "no_relevant_cases"}

    facts_text = _format_facts_for_prompt(facts)
    cases_output = []

    for item in retrieved_cases:
        metadata = item.get("metadata", {})
        case_title = str(metadata.get("case_title", "")).strip()
        court = str(metadata.get("court", "")).strip()
        date = str(metadata.get("date", "")).strip()
        # CRITICAL: source_url and attribution are copied programmatically from metadata
        source_url = str(metadata.get("source_url", "")).strip()
        attribution = str(metadata.get("attribution", "")).strip()
        reasoning_text = str(item.get("text", "")).strip()

        # Generic fallback explanation in case LLM parsing fails or raises
        fallback_explanation = (
            f"This precedent from {court or 'the court'} establishes legal principles "
            "relevant to the issues raised in the reported dispute."
        )
        explanation = fallback_explanation

        prompt = RELEVANCE_PROMPT_TEMPLATE.format(
            facts_text=facts_text,
            case_title=case_title,
            court=court,
            date=date,
            reasoning_text=reasoning_text,
        )

        try:
            raw_response = call_llm_structured(prompt)
            parsed = json.loads(raw_response)
            if isinstance(parsed, dict) and "relevance_explanation" in parsed:
                candidate_exp = str(parsed["relevance_explanation"]).strip()
                if candidate_exp:
                    explanation = candidate_exp
        except Exception as e:
            logger.warning(f"Landmark case explanation generation failed for '{case_title}': {e}")
            explanation = fallback_explanation

        cases_output.append({
            "case_title": case_title,
            "court": court,
            "date": date,
            "source_url": source_url,
            "attribution": attribution,
            "relevance_explanation": explanation,
        })

    return {
        "cases": cases_output,
        "status": "found",
    }
