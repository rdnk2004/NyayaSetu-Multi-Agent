"""
QA Agent (Question-Answering grounded in Retrieval)

Consumes a completed case brief from the Intake Agent:
  - Builds a natural-language query from the collected facts
  - Retrieves top candidate legal chunks from the vector store via retrieve()
  - Prompts the LLM with the citizen's facts and retrieved provisions
  - Strictly enforces that answers must ONLY be grounded in the retrieved chunks
    and cite exact section numbers
  - Responds with status "unclear" if chunks do not support an answer or if
    JSON parsing fails (never hallucinate / guess)
"""

import json
from llm_client import call_llm_structured
from retrieve import retrieve


QA_PROMPT_TEMPLATE = """You are a legal question-answering assistant for Indian Law. \
A citizen has provided facts regarding their legal situation. You are also provided with \
retrieved legal provisions (chunks) from the relevant Act.

Your task is to answer the citizen's legal inquiry based ONLY on the retrieved legal chunks.

Domain: {domain}

Citizen's Facts:
{facts_text}

Retrieved Legal Chunks:
{chunks_text}

Rules:
1. Answer ONLY using the information contained in the retrieved legal chunks above. Do NOT use outside knowledge, speculate, or guess.
2. Cite the exact section number(s) (e.g. "Section 2(11)", "Section 35") from the chunks that support your answer.
3. If none of the retrieved chunks provide enough information to answer the question, or if the chunks are not relevant, you MUST set "status" to "unclear", "cited_sections" to [], and "answer" to a brief explanation stating that the retrieved provisions do not cover the issue. Never guess or hallucinate.

Respond with ONLY a JSON object, no other text, in this exact format:
{{
  "answer": "<clear plain-language legal answer grounded only in the chunks, or brief explanation if unclear>",
  "cited_sections": ["<exact section number, e.g. Section 2(11)>"],
  "status": "<'answered' or 'unclear'>"
}}
"""


def _build_query_from_facts(facts: dict) -> str:
    """
    Build a natural-language search query from the citizen's collected facts.
    """
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


def _format_chunks_for_prompt(chunks: list[dict]) -> str:
    """Format candidate retrieved chunks with their exact section numbers and text."""
    if not chunks:
        return "No legal chunks retrieved."

    formatted_chunks = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        section = metadata.get("section", "Unknown")
        title = metadata.get("title", "")
        text = chunk.get("text", "").strip()

        sec_label = section if section.lower().startswith("section") else f"Section {section}"
        title_label = f" ({title})" if title else ""

        formatted_chunks.append(
            f"--- Chunk {i} [{sec_label}{title_label}] ---\n{text}"
        )

    return "\n\n".join(formatted_chunks)


def answer_question(case_brief: dict) -> dict:
    """
    Answers a citizen's legal inquiry using retrieved legal chunks and structured LLM generation.

    Args:
        case_brief: dict shaped like IntakeSession.to_case_brief() output
                    ({"domain": str, "facts": dict, "ready": bool})

    Returns:
        dict: {
            "answer": str,
            "cited_sections": list[str],
            "status": "answered" | "unclear",
            "retrieved_chunks": list[dict]
        }
    """
    if not isinstance(case_brief, dict):
        return {
            "answer": "",
            "cited_sections": [],
            "status": "unclear",
            "retrieved_chunks": [],
        }

    domain = case_brief.get("domain", "Unknown")
    facts = case_brief.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}

    query = _build_query_from_facts(facts)
    if not query:
        return {
            "answer": "",
            "cited_sections": [],
            "status": "unclear",
            "retrieved_chunks": [],
        }

    chunks = retrieve(query, top_k=5)
    if not chunks:
        return {
            "answer": "",
            "cited_sections": [],
            "status": "unclear",
            "retrieved_chunks": [],
        }

    prompt = QA_PROMPT_TEMPLATE.format(
        domain=domain,
        facts_text=_format_facts_for_prompt(facts),
        chunks_text=_format_chunks_for_prompt(chunks),
    )

    raw_response = call_llm_structured(prompt)

    try:
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        # Fail safe rather than silently guessing - matches query_understanding.py
        return {
            "answer": "",
            "cited_sections": [],
            "status": "unclear",
            "retrieved_chunks": chunks,
        }

    if not isinstance(parsed, dict):
        return {
            "answer": "",
            "cited_sections": [],
            "status": "unclear",
            "retrieved_chunks": chunks,
        }

    status = parsed.get("status", "unclear")
    if status not in ("answered", "unclear"):
        status = "unclear"

    answer = str(parsed.get("answer", "") or "").strip()
    raw_citations = parsed.get("cited_sections", [])
    if isinstance(raw_citations, list):
        cited_sections = [str(s).strip() for s in raw_citations if str(s).strip()]
    elif isinstance(raw_citations, str) and raw_citations.strip():
        cited_sections = [raw_citations.strip()]
    else:
        cited_sections = []
    
    cited_sections = [
        s[8:].strip() if s.lower().startswith("section ") else s
        for s in cited_sections
    ]

    return {
        "answer": answer,
        "cited_sections": cited_sections,
        "status": status,
        "retrieved_chunks": chunks,
    }
