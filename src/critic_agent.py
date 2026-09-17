"""
Critic Agent (Final Re-Verification & Quality Assurance Pass)

Acts as the last quality gate before legal information reaches a citizen:
1. Conducts a high-level sanity audit across the entire reasoning chain:
   - Does final_answer address what the citizen actually asked?
   - Is it internally consistent with the Debate Mechanism adjudication?
   - Does it overclaim ("definitely", "guaranteed", "always") beyond the
     warranted scope of the verified statutory sections?
2. Non-response pass-through:
   If verification_result.verified is False (already an unverified fallback),
   skips the LLM call entirely and returns the fallback answer unchanged.
3. Fail-safe design:
   The Critic is a quality check, not a hard blocking gate. If the LLM call fails
   or returns malformed output, it defaults to approved=True with the original
   verified answer intact.
"""

import logging
from typing import Any

from llm_client import call_llm_structured, safe_parse_llm_json
from models import CaseBrief, CitationVerificationResult, CriticResult, DebateResult
from pii_redaction import redact_pii

logger = logging.getLogger(__name__)


CRITIC_PROMPT_TEMPLATE = """You are an impartial legal quality auditor under Indian Law. \
A citizen has presented a legal problem, our system retrieved statutory provisions, verified citations, \
and conducted an adversarial debate and adjudication.

Your task is to perform a final quality and calibration check on the proposed Final Answer before it is sent to the citizen.

Citizen's Problem & Facts:
Domain: {domain}
{facts_text}

Verified Statutory Sections:
{verified_sections_text}

Debate Mechanism Adjudication:
{debate_summary_text}

Proposed Final Answer to Audit:
\"\"\"{proposed_answer}\"\"\"

Audit Criteria:
1. Grey-Zone & Internal Consistency:
   - If the Debate Mechanism determined that this case involves a genuine legal grey zone (is_grey_zone = True) \
with legitimate competing statutory interpretations, does the proposed answer acknowledge that ambiguity?
   - If the answer makes unqualified, definitive promises of victory or liability ("you will definitely win", \
"the seller is guaranteed liable") despite an active grey zone, flag this as a grey-zone conflict ("flagged_grey_zone_conflict": true) \
and provide a revised/softened "final_answer" that accurately communicates the uncertainty to the citizen.
2. Overclaiming & Grounding Scope:
   - Does the answer make sweeping absolute claims ("guaranteed", "100%", "definitely") that exceed the scope of the \
verified sections? (Note: standard statutory terms like "mandatory", "required by law", or "statutory duty" are acceptable \
if substantiated by the text).
3. Calibration:
   - If the proposed answer is well-calibrated and appropriately framed:
     "approved": true, "final_answer": <original proposed answer unchanged>, "flagged_grey_zone_conflict": false.
   - If the proposed answer overclaims or ignores a genuine grey zone:
     "approved": false, "final_answer": <revised and softened answer maintaining verified citations but properly conditioning certainty>, "flagged_grey_zone_conflict": <true if grey zone ignored, else false>.

Respond with ONLY a JSON object, no other text, in this exact format:
{{
  "approved": true,
  "final_answer": "<original answer unchanged, or revised/softened version if issues were found>",
  "critique_notes": "<concise explanation of what was checked and any issues identified>",
  "flagged_grey_zone_conflict": false
}}
"""


def _format_facts_for_prompt(facts: dict[str, Any]) -> str:
    """Format the citizen's facts into readable bullet points for the prompt."""
    if not facts or not isinstance(facts, dict):
        return "No specific facts provided."

    lines = []
    for k, v in facts.items():
        if v:
            clean_key = str(k).replace("_", " ").title()
            lines.append(f"- {clean_key}: {v}")

    return "\n".join(lines) if lines else "No specific facts provided."


def run_final_critique(
    case_brief: CaseBrief | dict,
    verification_result: CitationVerificationResult | dict,
    debate_result: DebateResult | dict | None,
) -> CriticResult:
    """
    Executes final quality critique and sanity check on the proposed legal answer.

    Args:
        case_brief: CaseBrief or dict with domain and facts
        verification_result: CitationVerificationResult or dict from verify_citations
        debate_result: DebateResult or dict from run_debate, or None if debate skipped/failed

    Returns:
        CriticResult: {
            "approved": bool,
            "final_answer": str,
            "critique_notes": str,
            "flagged_grey_zone_conflict": bool
        }
    """
    # 1. Defensively extract verification result fields
    if isinstance(verification_result, (CitationVerificationResult, dict)):
        is_verified = bool(verification_result.get("verified", False))
        orig_final_answer = str(verification_result.get("final_answer", "") or "").strip()
        verified_sections = list(verification_result.get("verified_sections", []) or [])
    else:
        is_verified = False
        orig_final_answer = ""
        verified_sections = []

    # 2. Non-response pass-through: if answer is already an unverified fallback,
    # skip LLM call entirely and return fallback unchanged.
    if not is_verified:
        logger.debug("Critic skipped: underlying answer is already unverified fallback.")
        return CriticResult(
            approved=True,
            final_answer=orig_final_answer,
            critique_notes="Skipped - underlying answer already unverified",
            flagged_grey_zone_conflict=False,
        )

    # 3. Extract case facts and domain
    domain = (
        str(case_brief.get("domain", "Unknown") or "Unknown")
        if isinstance(case_brief, (dict, CaseBrief))
        else "Unknown"
    )
    facts = (
        case_brief.get("facts", {})
        if isinstance(case_brief, (dict, CaseBrief))
        else {}
    )
    if not isinstance(facts, dict):
        facts = {}
    facts_text = _format_facts_for_prompt(facts)

    # 4. Extract and format debate adjudication context
    has_debate = debate_result is not None and isinstance(debate_result, (dict, DebateResult))
    if has_debate:
        is_grey_zone = bool(debate_result.get("is_grey_zone", False))
        judge_summary = str(debate_result.get("judge_summary", "") or "").strip()
        supported_side = debate_result.get("clearly_supported_side")
        debate_summary_text = (
            f"Is Grey Zone: {is_grey_zone}\n"
            f"Clearly Supported Side: {supported_side}\n"
            f"Judge Summary: {judge_summary}"
        )
    else:
        is_grey_zone = False
        debate_summary_text = "Debate Result: None (not performed or skipped)"

    # 5. Format verified sections
    verified_sections_text = (
        ", ".join(f"Section {s}" for s in verified_sections)
        if verified_sections
        else "No sections verified"
    )

    # 6. Build prompt and invoke structured LLM
    prompt = CRITIC_PROMPT_TEMPLATE.format(
        domain=domain,
        facts_text=facts_text,
        verified_sections_text=verified_sections_text,
        debate_summary_text=debate_summary_text,
        proposed_answer=orig_final_answer,
    )

    try:
        raw_response = call_llm_structured(prompt)
    except Exception as e:
        logger.warning(
            "Critic LLM call failed: %s. Failing safe with approved=True and original answer.",
            e,
            exc_info=True,
        )
        return CriticResult(
            approved=True,
            final_answer=orig_final_answer,
            critique_notes=f"Critic LLM call failed ({e}); failing safe with original answer.",
            flagged_grey_zone_conflict=False,
        )

    # 7. Safe JSON parse with fail-safe fallback
    parsed = safe_parse_llm_json(raw_response, fallback={})
    if not parsed or not isinstance(parsed, dict):
        logger.warning(
            "Critic LLM returned unparseable output. Failing safe with approved=True and original answer."
        )
        return CriticResult(
            approved=True,
            final_answer=orig_final_answer,
            critique_notes="Critic LLM returned unparseable output; failing safe with original answer.",
            flagged_grey_zone_conflict=False,
        )

    approved = bool(parsed.get("approved", True))
    revised_answer = str(parsed.get("final_answer", "") or "").strip()
    final_answer = revised_answer if revised_answer else orig_final_answer
    critique_notes = str(parsed.get("critique_notes", "") or "").strip()
    if not critique_notes:
        critique_notes = "Critique evaluation completed successfully."

    # flagged_grey_zone_conflict should only ever be checked/set when debate_result is not None
    raw_flagged = bool(parsed.get("flagged_grey_zone_conflict", False))
    flagged_grey_zone_conflict = raw_flagged if has_debate else False

    return CriticResult(
        approved=approved,
        final_answer=final_answer,
        critique_notes=critique_notes,
        flagged_grey_zone_conflict=flagged_grey_zone_conflict,
    )
