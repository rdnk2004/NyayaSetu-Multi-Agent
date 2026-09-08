# NyayaSetu — Multi-Agent AI for Indian Law

A multi-agent AI system that helps citizens understand their legal
situation in plain language, without needing a lawyer to explain the
basics — while still directing them to a lawyer when a situation is
high-stakes.

**Core design principle:** the system never answers from an LLM's own
trained memory. Every legal claim must trace back to a retrieved,
dated, source-linked document from the actual Act or precedent-setting
case law. Hallucination is treated as a retrieval and verification
problem, not something solved by clever prompting.

Scoped to two legal domains for this phase — broad coverage across
"every law" is an explicit non-goal.

---

## Architecture

The system is a pipeline of specialized agents, each with a narrow job:

| # | Agent | Status |
|---|-------|--------|
| 1 | Query Understanding Agent | ✅ Built — skeleton |
| 2 | Intelligent Intake Agent | ✅ Built — skeleton |
| 3 | Retrieval Agent (RAG) | ✅ Built — **validated** |
| 4 | Landmark Case Learning Agent | ✅ Built — API ingestion & landmark corpus |
| 5 | Citation Verification Agent | ✅ Built — skeleton |
| 6 | Pipeline Orchestrator | ✅ Built — skeleton |
| 7 | Adversarial Debate Mechanism (grey-zone detection) | ⬜ Not started |
| 8 | Document-Drafting Agent | ⬜ Not started |
| 9 | Risk / Escalation Agent | ⬜ Not started |
| 10 | Plain-Language Explainer Agent | ⬜ Not started |
| 11 | Adversarial Critic Agent | ⬜ Not started |

**"Skeleton" vs "validated"** — an important distinction, not a
formality: *skeleton* means the code's logic is correct and covered by
unit tests, but those tests mock the LLM call, so the agent has never
actually been run against real model output. *Validated* means it's
been tested against real data end-to-end. The Retrieval Agent and Case Law
Ingestion Pipeline have cleared that bar.

There is also a scaffolding module, `qa_agent.py`, built as a
bridge that lets Retrieval and Citation Verification be tested together
before the Explainer Agent takes over final answer delivery.

---

## Progress so far

**Retrieval pipeline (built and validated):**
- Direct PDF text extraction (`extract_pdf.py`) — no OCR needed, since
  source Acts are digital PDFs with selectable text. Correctly parses
  all sections of the Consumer Protection Act, 2019 (107/107, no gaps
  or duplicates).
- Legal-structure-aware chunking (`chunk_text.py`) — splits on numbered
  sub-clauses (e.g. definitions, sub-sections) rather than raw word
  count, so each chunk is one atomic, precisely citable legal unit
  (e.g. `2(11)`, not a fragment cut mid-sentence).
- Embedding + vector store (`embed_and_store.py`) — local, free
  embeddings (`multi-qa-mpnet-base-dot-v1`, tuned for question→passage
  matching) stored in Chroma with inner-product distance.
- Retrieval function (`retrieve.py`) — tested against real queries on
  the real 107-section corpus; correct answer lands in the top 5
  results consistently.

**Case law ingestion pipeline (`fetch_case_law.py`):**
- Official Indian Kanoon API integration with Token and HMAC crypto auth.
- Real-time per-request rate card logging in INR (Search: ₹0.50, Doc: ₹0.20).
- "Powered by IKanoon" attribution handling per their API terms of service.
- Full ratio decidendi reasoning extraction via Gemini LLM with algorithmic fallback.
- Ingested 10 landmark Consumer Protection Act precedents into `data/raw/case_law/` across deficiency in service, product liability, and commission jurisdiction disputes.
- Local response caching prevents redundant API charges.

**Intake pipeline (built, logic-tested with mocked LLM calls):**
- `domain_checklists.py` — explicit, inspectable checklist of required
  facts per domain. "Confidence" is mechanical (checklist full), not
  an opaque LLM self-report.
- `query_understanding.py` — single-pass extraction of domain + known
  facts from a citizen's first message. Never guesses — leaves a field
  blank rather than inferring an unstated fact.
- `intake_agent.py` — asks one follow-up question at a time for the
  highest-priority missing field, stops once the checklist is
  satisfied (or a safety-valve question limit is hit), runs a final
  "anything critical missing?" pass before handoff.

**Answer + verification pipeline (built, logic-tested with mocked LLM calls):**
- `qa_agent.py` — takes a completed case brief, retrieves candidate
  chunks, and answers strictly grounded in retrieved text, citing
  exact section numbers. Returns "unclear" rather than guessing when
  retrieved chunks don't support an answer. Exposes the retrieved
  chunks it used, so downstream verification doesn't need to
  re-retrieve.
- `citation_verification_agent.py` — cross-checks every cited section
  against what was actually retrieved (exact match), then uses an LLM
  judgment pass to confirm the cited text genuinely supports the
  claim. Any citation that fails either check causes the whole answer
  to fall back to a safe "needs manual review" response rather than
  reaching the user unverified.

**Orchestrator pipeline (`orchestrator.py`):**
- Resumable multi-turn state machine managing the full inquiry lifecycle.
- Automatically routes user input through Query Understanding → Intelligent Intake → Retrieval & Grounded QA → Citation Verification.
- Drives sessions turn-by-turn via `.start()`, `.answer_question()`, and `.proceed()`.

**LLM client (`llm_client.py`):** Gemini API integration with real
cost/safety guardrails — prompt caching, session call budget cap,
per-minute rate limiting, retry with backoff.

**Domains:**
- Consumer Protection Act, 2019 — fully extracted, chunked, and validated.
- Precedent Case Law — landmark Consumer Protection judgments ingested.
- Second domain — not yet chosen / sourced.

**Tests:** `test_intake_flow.py`, `test_llm_client_guards.py`,
`test_qa_agent.py`, `test_citation_verification_agent.py`,
`test_orchestrator.py` — 23 tests, all passing.

---

## Project structure

```
├── data/
│   ├── raw/
│   │   ├── consumer-protection-act-2019_sections.txt   # section-tagged Act
│   │   └── case_law/                                   # structured landmark cases (.txt)
│   ├── processed/                                      # chunks.json (generated)
│   └── chroma_db/                                      # vector store (generated, gitignored)
├── src/
│   ├── extract_pdf.py                  # PDF -> section-tagged .txt
│   ├── chunk_text.py                   # sections -> retrieval chunks
│   ├── embed_and_store.py              # chunks -> embeddings -> vector store
│   ├── retrieve.py                     # query -> top-k relevant chunks
│   ├── fetch_case_law.py               # Indian Kanoon API ingestion pipeline
│   ├── domain_checklists.py            # required-fact checklist per domain
│   ├── query_understanding.py          # first-pass domain + fact extraction
│   ├── intake_agent.py                 # follow-up question state machine
│   ├── qa_agent.py                     # retrieval-grounded answer generation
│   ├── citation_verification_agent.py  # citation cross-check before output
│   ├── orchestrator.py                 # end-to-end multi-turn state machine
│   └── llm_client.py                   # Gemini API wrapper + guardrails
├── tests/
│   ├── test_intake_flow.py
│   ├── test_llm_client_guards.py
│   ├── test_qa_agent.py
│   ├── test_citation_verification_agent.py
│   └── test_orchestrator.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in GEMINI_API_KEY & INDIAN_KANOON_API_KEY
```

## Running the retrieval pipeline

```bash
python src/chunk_text.py
python src/embed_and_store.py   # downloads the embedding model on first run
python src/retrieve.py
```

## Running case law ingestion

```bash
python src/fetch_case_law.py --limit 10
```

## Running the tests

```bash
PYTHONPATH=src python -m pytest tests/ -v
```